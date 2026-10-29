"""SQL validator (safety layer 2): parse with sqlglot and allow only safe, read-only SQL.

Rules, in order:
1. Size and characters: at most 10,000 characters; no control or invisible format
   characters; outside string literals, ASCII only (stops lookalike-letter tricks).
2. Exactly one statement, and it is a query (SELECT, WITH ... SELECT, UNION, ...).
3. No write, DDL, utility, or locking node anywhere in the tree (catches
   data-modifying CTEs, SELECT ... INTO, FOR UPDATE, COPY, SET, CALL, ...).
4. Functions: unknown (non-standard) functions must be on an allow-list; every
   function name is also checked against a deny-list (pg_*, set_config, ...).
5. Tables: only views in the data dictionary, in schema `analytics` (or CTE names).
6. Columns: every column must exist in the dictionary (stars are expanded), and
   columns flagged as personal data (pii) are rejected.

The executor runs `ValidatedSQL.sql`, which is regenerated from the parsed tree with
comments removed, so Postgres only ever sees what was validated.
"""

import re
import unicodedata
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError, TokenError
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope
from sqlglot.schema import MappingSchema
from sqlglot.tokens import TokenType

from sql_analyst.dictionary.models import Dictionary
from sql_analyst.safety.errors import SQLRejected

DIALECT = "postgres"
SCHEMA = "analytics"
MAX_SQL_CHARS = 10_000

# Node types that must never appear anywhere in a query tree.
_FORBIDDEN_NODE_NAMES = (
    "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "TruncateTable",
    "Command", "Set", "SetItem", "Transaction", "Commit", "Rollback", "Copy", "Into", "Lock",
    "Grant", "Revoke", "Use", "Pragma", "Describe", "Analyze", "Kill", "LoadData", "Refresh",
    "Cache", "Uncache", "Comment", "Summarize",
)  # fmt: skip
FORBIDDEN_NODES = tuple(t for name in _FORBIDDEN_NODE_NAMES if (t := getattr(exp, name, None)))

# Postgres functions that sqlglot does not model (they parse as exp.Anonymous) and are
# safe for analytics. Anything else unknown is rejected.
ALLOWED_ANONYMOUS_FUNCTIONS = frozenset(
    [
        "date_part",
        "to_date",
        "to_timestamp",
        "make_date",
        "make_timestamp",
        "make_timestamptz",
        "make_interval",
        "age",
        "justify_days",
        "justify_hours",
        "date_bin",
        "isfinite",
        "initcap",
        "split_part",
        "strpos",
        "btrim",
        "ltrim",
        "rtrim",
        "lpad",
        "rpad",
        "reverse",
        "translate",
        "format",
        "char_length",
        "octet_length",
        "regexp_replace",
        "regexp_match",
        "regexp_matches",
        "regexp_split_to_array",
        "string_to_array",
        "array_to_string",
        "array_length",
        "cardinality",
        "array_position",
        "width_bucket",
        "generate_series",
        "unnest",
        "percent_rank",
        "cume_dist",
        "ntile",
        "nth_value",
        "mode",
        "bool_and",
        "bool_or",
        "every",
        "stddev",
        "stddev_pop",
        "stddev_samp",
        "var_pop",
        "var_samp",
        "variance",
        "corr",
        "covar_pop",
        "covar_samp",
        "regr_slope",
        "regr_intercept",
        "regr_r2",
        "div",
        "mod",
        "trunc",
        "sign",
        "log",
        "ln",
        "exp",
        "power",
        "sqrt",
        "cbrt",
        "ceiling",
        "to_number",
        "round_half_even",
        "json_build_object",
        "jsonb_build_object",
        "json_agg",
        "jsonb_agg",
    ]
)

# Checked against every function's name (typed or not): system, file, network,
# configuration, large-object, and remote-database functions.
DENIED_FUNCTION = re.compile(
    r"^(pg_|lo_|dblink|set_config$|current_setting$|txid_|has_\w*_privilege$|inet_|"
    r"(query|table|cursor|schema|database)_to_xml|xpath|version$|current_(user|role|database|"
    r"schema|schemas|catalog|version)$|session_user$|user$|nextval$|setval$|currval$|lastval$|"
    r"set_|current_query$|row_security_active$)",
    re.IGNORECASE,
)

_STRING_TOKENS = {
    t
    for name in (
        "STRING",
        "NATIONAL_STRING",
        "RAW_STRING",
        "HEREDOC_STRING",
        "BYTE_STRING",
        "BIT_STRING",
        "HEX_STRING",
        "UNICODE_STRING",
    )
    if (t := getattr(TokenType, name, None))
}


@dataclass(frozen=True)
class ValidatedSQL:
    """SQL that passed validation, ready for the executor."""

    sql: str  # regenerated from the AST, comments removed
    views: frozenset[str]
    columns: frozenset[tuple[str, str]]  # (view, column) pairs read by the query


class SQLValidator:
    """Validates model- or user-written SQL against the data dictionary."""

    def __init__(self, dictionary: Dictionary, max_chars: int = MAX_SQL_CHARS):
        self.max_chars = max_chars
        self.views = {v.name: v for v in dictionary.views}
        self.pii = {(v.name, c.name) for v in dictionary.views for c in v.columns if c.pii}
        self.schema = MappingSchema(
            {SCHEMA: {v.name: {c.name: c.type for c in v.columns} for v in dictionary.views}},
            dialect=DIALECT,
        )

    def validate(self, sql: str) -> ValidatedSQL:
        self._check_characters(sql)
        stmt = self._parse_single(sql)
        self._check_statement_type(stmt)
        self._check_forbidden_nodes(stmt)
        self._check_functions(stmt)
        self._check_casts(stmt)
        views = self._check_tables(stmt)
        columns = self._check_columns(stmt)
        return ValidatedSQL(
            sql=stmt.sql(dialect=DIALECT, comments=False),
            views=frozenset(views),
            columns=frozenset(columns),
        )

    # -- 1. characters -------------------------------------------------------------
    def _check_characters(self, sql: str) -> None:
        if not sql or not sql.strip():
            raise SQLRejected("The SQL is empty.", "empty")
        if len(sql) > self.max_chars:
            raise SQLRejected(f"The SQL is longer than {self.max_chars} characters.", "too_long")
        for ch in sql:
            cat = unicodedata.category(ch)
            if (cat == "Cc" and ch not in "\t\n\r") or cat in ("Cf", "Co", "Cs"):
                raise SQLRejected(
                    f"The SQL contains a control or invisible character (U+{ord(ch):04X}).",
                    "bad_character",
                )
        try:
            tokens = sqlglot.Dialect.get_or_raise(DIALECT).tokenize(sql)
        except (TokenError, ValueError) as e:
            raise SQLRejected(f"The SQL could not be tokenized: {e}", "parse_error") from e
        for tok in tokens:
            if tok.token_type not in _STRING_TOKENS and not tok.text.isascii():
                raise SQLRejected(
                    f"Non-ASCII characters are only allowed inside string literals: {tok.text!r}.",
                    "non_ascii",
                )

    # -- 2. one query statement ----------------------------------------------------
    def _parse_single(self, sql: str) -> exp.Expression:
        try:
            statements = [s for s in sqlglot.parse(sql, read=DIALECT) if s is not None]
        except (ParseError, TokenError) as e:
            raise SQLRejected(
                f"The SQL could not be parsed: {_first_line(e)}", "parse_error"
            ) from e
        if not statements:
            raise SQLRejected("The SQL is empty.", "empty")
        if len(statements) > 1:
            raise SQLRejected(
                "Only one SQL statement is allowed; remove the extra statements.",
                "multiple_statements",
            )
        return statements[0]

    def _check_statement_type(self, stmt: exp.Expression) -> None:
        root = stmt.unnest() if isinstance(stmt, exp.Subquery) else stmt
        if not isinstance(root, (exp.Select, exp.SetOperation)):
            raise SQLRejected(
                f"Only SELECT queries are allowed (got {type(root).__name__.upper()}).",
                "not_select",
            )

    def _check_forbidden_nodes(self, stmt: exp.Expression) -> None:
        for node in stmt.walk():
            if isinstance(node, FORBIDDEN_NODES):
                raise SQLRejected(
                    f"{type(node).__name__.upper()} is not allowed: the database is read-only and "
                    "only plain SELECT queries can run.",
                    "forbidden_statement",
                )

    # -- 4. functions --------------------------------------------------------------
    def _check_functions(self, stmt: exp.Expression) -> None:
        for func in stmt.find_all(exp.Func):
            if isinstance(func, exp.Anonymous):
                name = func.name.lower()
                if DENIED_FUNCTION.match(name) or name not in ALLOWED_ANONYMOUS_FUNCTIONS:
                    raise SQLRejected(f"Function {name}() is not allowed.", "forbidden_function")
            else:
                names = {func.sql_name().lower(), _rendered_name(func)}
                if any(DENIED_FUNCTION.match(n) for n in names if n):
                    raise SQLRejected(
                        f"Function {func.sql_name().lower()}() is not allowed.",
                        "forbidden_function",
                    )
            parent = func.parent
            if isinstance(parent, exp.Dot) and parent.expression is func:
                raise SQLRejected(
                    "Schema-qualified function calls are not allowed.", "forbidden_function"
                )

    def _check_casts(self, stmt: exp.Expression) -> None:
        for dtype in stmt.find_all(exp.DataType):
            name = dtype.sql(dialect=DIALECT).lower()
            if name.startswith("reg") or name.startswith("pg_"):
                raise SQLRejected(f"Casting to {name} is not allowed.", "forbidden_cast")

    # -- 5. tables -----------------------------------------------------------------
    def _check_tables(self, stmt: exp.Expression) -> set[str]:
        cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
        used = set()
        for table in stmt.find_all(exp.Table):
            if isinstance(table.this, exp.Func):  # table function, e.g. generate_series(...)
                continue
            name, db, catalog = table.name.lower(), table.db.lower(), table.catalog
            if not db and name in cte_names:
                continue
            if catalog or (db and db != SCHEMA) or name not in self.views:
                shown = ".".join(p for p in (catalog, db, name) if p)
                raise SQLRejected(
                    f"Table {shown} is not allowed. Use only the {SCHEMA} views in the data "
                    "dictionary (for example analytics.fact_orders).",
                    "forbidden_table",
                )
            used.add(name)
        return used

    # -- 6. columns ----------------------------------------------------------------
    def _check_columns(self, stmt: exp.Expression) -> set[tuple[str, str]]:
        try:
            qualified = qualify(
                stmt.copy(),
                schema=self.schema,
                db=SCHEMA,
                dialect=DIALECT,
                validate_qualify_columns=True,
                quote_identifiers=False,
                identify=False,
            )
        except OptimizeError as e:
            raise SQLRejected(
                f"Unknown or ambiguous column: {_first_line(e)}", "unknown_column"
            ) from e
        used = set()
        for scope in traverse_scope(qualified):
            for column in scope.columns:
                source = scope.sources.get(column.table)
                if isinstance(source, exp.Table) and source.db.lower() == SCHEMA:
                    key = (source.name.lower(), column.name.lower())
                    if key in self.pii:
                        raise SQLRejected(
                            f"Column {key[0]}.{key[1]} contains personal data and cannot be queried.",
                            "pii_column",
                        )
                    used.add(key)
        return used


def _rendered_name(func: exp.Func) -> str:
    """The function name as it appears in generated Postgres SQL (e.g. TO_CHAR)."""
    rendered = func.sql(dialect=DIALECT)
    return re.split(r"[\s(]", rendered, maxsplit=1)[0].lower()


def _first_line(e: Exception) -> str:
    return str(e).strip().splitlines()[0][:300]
