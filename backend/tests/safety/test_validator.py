"""Safety layer 2: the SQL validator. No database needed.

ADVERSARIAL must all be rejected (with the expected reason); ALLOWED must all pass,
so the validator does not block ordinary analytical SQL.
"""

import pytest

from sql_analyst.dictionary.loader import load_dictionary
from sql_analyst.dictionary.models import Column, Dictionary
from sql_analyst.safety.errors import SQLRejected
from sql_analyst.safety.validator import SQLValidator

DICTIONARY = load_dictionary()
V = SQLValidator(DICTIONARY)

NOT_SELECT = ("not_select", "forbidden_statement")
STACKED = ("multiple_statements",)
FUNC = ("forbidden_function",)
TABLE = ("forbidden_table",)
CHARS = ("non_ascii", "bad_character")

# (id, sql, acceptable rejection codes)
ADVERSARIAL = [
    # --- writes and DDL -------------------------------------------------------------
    ("dml_delete", "DELETE FROM analytics.fact_orders", NOT_SELECT),
    ("dml_update", "UPDATE analytics.fact_orders SET status = 'completed'", NOT_SELECT),
    ("dml_insert", "INSERT INTO analytics.dim_channel VALUES (9, 'x', 'x', true)", NOT_SELECT),
    (
        "dml_merge",
        "MERGE INTO analytics.dim_store t USING analytics.dim_store s ON t.store_id = s.store_id WHEN MATCHED THEN DELETE",
        (*NOT_SELECT, "parse_error"),
    ),
    ("ddl_drop_view", "DROP VIEW analytics.fact_orders", NOT_SELECT),
    ("ddl_drop_core", "DROP TABLE core.customers CASCADE", NOT_SELECT),
    ("ddl_create_table", "CREATE TABLE analytics.x (id int)", NOT_SELECT),
    ("ddl_create_as", "CREATE TABLE stolen AS SELECT * FROM analytics.dim_customer", NOT_SELECT),
    ("ddl_alter", "ALTER TABLE core.orders DISABLE ROW LEVEL SECURITY", NOT_SELECT),
    ("ddl_truncate", "TRUNCATE analytics.fact_orders", NOT_SELECT),
    ("ddl_grant", "GRANT SELECT ON ALL TABLES IN SCHEMA core TO nlq_reader", NOT_SELECT),
    (
        "ddl_create_function",
        "CREATE FUNCTION f() RETURNS int AS $$ SELECT 1 $$ LANGUAGE sql",
        NOT_SELECT,
    ),
    ("ddl_create_extension", "CREATE EXTENSION dblink", NOT_SELECT),
    # --- writes hidden inside a query ---------------------------------------------------
    (
        "cte_delete",
        "WITH d AS (DELETE FROM analytics.fact_orders RETURNING *) SELECT count(*) FROM d",
        NOT_SELECT,
    ),
    (
        "cte_update",
        "WITH u AS (UPDATE analytics.fact_orders SET total_amount = 0 RETURNING 1) SELECT * FROM u",
        NOT_SELECT,
    ),
    (
        "cte_insert",
        "WITH i AS (INSERT INTO analytics.dim_channel VALUES (9,'x','x',true) RETURNING 1) SELECT * FROM i",
        NOT_SELECT,
    ),
    ("select_into", "SELECT * INTO stolen FROM analytics.dim_customer", NOT_SELECT),
    ("lock_for_update", "SELECT * FROM analytics.dim_store FOR UPDATE", NOT_SELECT),
    ("lock_for_share", "SELECT * FROM analytics.dim_store FOR SHARE", NOT_SELECT),
    (
        "lock_for_no_key_update",
        "SELECT * FROM analytics.dim_store FOR NO KEY UPDATE",
        (*NOT_SELECT, "parse_error"),
    ),
    # --- utility and session statements --------------------------------------------------
    ("set_timeout", "SET statement_timeout = 0", NOT_SELECT),
    ("set_role", "SET ROLE postgres", NOT_SELECT),
    ("set_scope", "SET app.region_ids = 'all'", NOT_SELECT),
    ("reset_all", "RESET ALL", (*NOT_SELECT, "parse_error")),
    ("begin", "BEGIN", NOT_SELECT),
    ("commit", "COMMIT", NOT_SELECT),
    ("copy_to_file", "COPY analytics.dim_store TO '/tmp/stores.csv'", NOT_SELECT),
    (
        "copy_from_program",
        "COPY analytics.dim_store FROM PROGRAM 'id'",
        (*NOT_SELECT, "parse_error"),
    ),
    ("call", "CALL do_something()", NOT_SELECT),
    ("explain_analyze", "EXPLAIN ANALYZE SELECT 1", NOT_SELECT),
    ("vacuum", "VACUUM FULL", (*NOT_SELECT, "parse_error")),
    ("do_block", "DO $$ BEGIN PERFORM pg_sleep(10); END $$", (*NOT_SELECT, "parse_error")),
    ("prepare", "PREPARE p AS SELECT 1", (*NOT_SELECT, "parse_error")),
    ("lock_table", "LOCK TABLE analytics.fact_orders", (*NOT_SELECT, "parse_error")),
    ("values_root", "VALUES (1), (2)", NOT_SELECT),
    # --- stacked statements ---------------------------------------------------------------
    ("stacked_delete", "SELECT 1; DELETE FROM analytics.fact_orders", STACKED),
    ("stacked_no_space", "SELECT 1;DROP VIEW analytics.fact_orders", STACKED),
    ("stacked_two_selects", "SELECT 1; SELECT 2", STACKED),
    ("stacked_newline", "SELECT 1\n;\nTRUNCATE analytics.fact_orders", STACKED),
    ("stacked_double_semicolon", "SELECT 1;;DELETE FROM analytics.fact_orders", STACKED),
    # --- comment tricks ---------------------------------------------------------------------
    (
        "comment_line_then_stack",
        "SELECT 1 -- harmless\n; DELETE FROM analytics.fact_orders",
        STACKED,
    ),
    ("comment_block_prefix", "/* report */ DELETE FROM analytics.fact_orders", NOT_SELECT),
    ("comment_hides_semicolon", "SELECT 1 /* ; */ ; DROP VIEW analytics.fact_orders", STACKED),
    (
        "comment_nested",
        "SELECT 1 /* /* */ ; DELETE FROM analytics.fact_orders; /* */",
        (*STACKED, "parse_error"),
    ),
    ("comment_glued", "SELECT/**/1;/**/DELETE/**/FROM/**/analytics.fact_orders", STACKED),
    # --- Unicode and invisible characters ------------------------------------------------------
    ("unicode_fullwidth_semicolon", "SELECT 1\uff1b DELETE FROM analytics.fact_orders", CHARS),
    (
        "unicode_zero_width_space",
        "SELECT 1; DE\u200bLETE FROM analytics.fact_orders",
        (*CHARS, *STACKED),
    ),
    ("unicode_cyrillic_e_in_keyword", "S\u0415LECT * FROM analytics.dim_store", CHARS),
    ("unicode_cyrillic_o_in_table", "SELECT * FROM analytics.fact_\u043erders", CHARS),
    ("unicode_rtl_override", "SELECT * FROM analytics.dim_store \u202e--", CHARS),
    ("unicode_null_byte", "SELECT 1\x00; DELETE FROM analytics.fact_orders", CHARS),
    ("unicode_quoted_identifier", 'SELECT "st\u043ere_id" FROM analytics.dim_store', CHARS),
    # --- time and denial of service -----------------------------------------------------------
    ("sleep", "SELECT pg_sleep(10)", FUNC),
    ("sleep_for", "SELECT pg_sleep_for('10 seconds')", FUNC),
    (
        "sleep_in_subquery",
        "SELECT * FROM analytics.dim_store WHERE store_id = (SELECT 1 FROM (SELECT pg_sleep(10)) s)",
        FUNC,
    ),
    ("sleep_schema_qualified", "SELECT pg_catalog.pg_sleep(10)", FUNC),
    # --- file, system, network, configuration functions -------------------------------------
    ("read_file", "SELECT pg_read_file('/etc/passwd')", FUNC),
    ("read_binary_file", "SELECT pg_read_binary_file('/etc/passwd')", FUNC),
    ("ls_dir", "SELECT * FROM pg_ls_dir('/')", FUNC),
    ("stat_file", "SELECT pg_stat_file('/etc/passwd')", FUNC),
    ("lo_import", "SELECT lo_import('/etc/passwd')", FUNC),
    ("lo_export", "SELECT lo_export(1, '/tmp/x')", FUNC),
    ("dblink", "SELECT * FROM dblink('host=evil', 'select 1') AS t(x int)", FUNC),
    ("query_to_xml", "SELECT query_to_xml('select * from core.customers', true, true, '')", FUNC),
    ("terminate_backend", "SELECT pg_terminate_backend(1)", FUNC),
    ("reload_conf", "SELECT pg_reload_conf()", FUNC),
    (
        "set_config_scope",
        "SELECT set_config('app.region_ids', 'all', true), count(*) FROM analytics.fact_orders",
        FUNC,
    ),
    (
        "set_config_in_cte",
        "WITH s AS (SELECT set_config('app.region_ids', 'all', true)) SELECT count(*) FROM analytics.fact_orders, s",
        FUNC,
    ),
    ("current_setting", "SELECT current_setting('app.region_sig')", FUNC),
    ("version", "SELECT version()", FUNC),
    ("current_user", "SELECT current_user", FUNC),
    ("inet_server_addr", "SELECT inet_server_addr()", FUNC),
    ("txid_current", "SELECT txid_current()", FUNC),
    ("nextval", "SELECT nextval('x')", FUNC),
    ("unknown_function", "SELECT my_udf(1)", FUNC),
    ("schema_qualified_udf", "SELECT analytics.my_udf(1)", FUNC),
    # --- system catalogs and other schemas ---------------------------------------------------
    ("catalog_pg_user", "SELECT * FROM pg_catalog.pg_user", TABLE),
    ("catalog_pg_shadow", "SELECT * FROM pg_shadow", TABLE),
    ("catalog_pg_authid", "SELECT rolname, rolpassword FROM pg_authid", TABLE),
    ("catalog_pg_roles", "SELECT * FROM pg_roles", TABLE),
    ("catalog_pg_class", "SELECT relname FROM pg_class", TABLE),
    ("catalog_stat_activity", "SELECT query FROM pg_stat_activity", TABLE),
    ("info_schema_tables", "SELECT table_name FROM information_schema.tables", TABLE),
    (
        "info_schema_columns",
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'core'",
        TABLE,
    ),
    ("regclass_cast", "SELECT 'pg_authid'::regclass", ("forbidden_cast",)),
    ("retrieval_index", "SELECT content, payload FROM retrieval.chunks", TABLE),
    ("retrieval_values", "SELECT value FROM retrieval.column_values", TABLE),
    ("core_customers", "SELECT full_name, email FROM core.customers", TABLE),
    (
        "core_join",
        "SELECT o.order_id, c.email FROM analytics.fact_orders o JOIN core.customers c USING (customer_id)",
        TABLE,
    ),
    (
        "core_in_subquery",
        "SELECT * FROM analytics.dim_store WHERE region_id IN (SELECT region_id FROM core.customers)",
        TABLE,
    ),
    ("rls_signing_key", "SELECT key FROM rls.signing_key", TABLE),
    ("quoted_core", 'SELECT * FROM "core"."customers"', TABLE),
    ("three_part_name", "SELECT * FROM arunika.core.customers", TABLE),
    ("public_schema", "SELECT * FROM public.anything", TABLE),
    ("unknown_view", "SELECT * FROM analytics.secret_view", TABLE),
    # --- columns and personal data ----------------------------------------------------------
    ("pii_customer_email", "SELECT email FROM analytics.dim_customer", ("unknown_column",)),
    ("pii_customer_name", "SELECT c.full_name FROM analytics.dim_customer c", ("unknown_column",)),
    (
        "pii_employee_salary",
        "SELECT monthly_salary_idr FROM analytics.dim_employee",
        ("unknown_column",),
    ),
    (
        "pii_supplier_contact",
        "SELECT contact_email FROM analytics.dim_supplier",
        ("unknown_column",),
    ),
    (
        "unknown_column_in_where",
        "SELECT store_id FROM analytics.dim_store WHERE phone IS NOT NULL",
        ("unknown_column",),
    ),
    # --- size and emptiness ---------------------------------------------------------------------
    ("too_long", "SELECT 1 AS x" + " " * 10_000, ("too_long",)),
    ("empty", "   ", ("empty",)),
    ("only_semicolons", ";;", ("empty", "parse_error")),
]

ALLOWED = [
    *(m.sql for m in DICTIONARY.glossary),
    "SELECT (ordered_at AT TIME ZONE 'Asia/Jakarta')::date AS d, count(*) FROM analytics.fact_orders GROUP BY 1 ORDER BY 1",
    "SELECT count(*) FILTER (WHERE status = 'cancelled') AS cancelled FROM fact_orders",
    "SELECT DISTINCT ON (store_id) store_id, ordered_at FROM analytics.fact_orders ORDER BY store_id, ordered_at DESC",
    "SELECT to_char(date_trunc('month', o.ordered_at AT TIME ZONE 'Asia/Jakarta'), 'YYYY-MM') AS m, sum(o.total_amount) FROM analytics.fact_orders o WHERE o.status <> 'cancelled' GROUP BY 1",
    "SELECT g::date AS d FROM generate_series(DATE '2025-01-01', DATE '2025-01-31', INTERVAL '1 day') AS g",
    "SELECT * FROM analytics.dim_store",
    "SELECT r.city, percentile_cont(0.5) WITHIN GROUP (ORDER BY o.total_amount) FROM analytics.fact_orders o JOIN analytics.dim_store s ON s.store_id = o.store_id JOIN analytics.dim_region r ON r.region_id = s.region_id GROUP BY r.city",
    "WITH m AS (SELECT store_id, sum(total_amount) AS rev FROM analytics.fact_orders GROUP BY store_id) SELECT s.store_name, m.rev, rank() OVER (ORDER BY m.rev DESC) FROM m JOIN analytics.dim_store s USING (store_id)",
    "SELECT category_name FROM analytics.dim_category WHERE category_name ILIKE '%elektronik%' UNION SELECT category_name_id FROM analytics.dim_category",
    "SELECT d.fiscal_year, d.fiscal_quarter, count(*) FROM analytics.fact_orders o JOIN analytics.dim_date d ON d.date_key = (o.ordered_at AT TIME ZONE 'Asia/Jakarta')::date WHERE d.fiscal_year = 2025 GROUP BY 1, 2",
    "SELECT store_id, extract(year FROM ordered_at) AS y, round(avg(total_amount), 0) FROM analytics.fact_orders GROUP BY 1, 2 HAVING count(*) > 10 LIMIT 5",
    "SELECT coalesce(sum(r.refund_amount_idr), 0) FROM analytics.fact_returns r WHERE r.returned_at >= now() - interval '90 days'",
    "SELECT ticket_number FROM analytics.fact_support_tickets WHERE subject ILIKE '%belum sampai — tolong%'",
    "SELECT 1 -- a trailing comment is fine",
    "SELECT store_id FROM analytics.dim_store;",
]


@pytest.mark.parametrize(("case_id", "sql", "codes"), ADVERSARIAL, ids=[c[0] for c in ADVERSARIAL])
def test_adversarial_sql_is_rejected(case_id, sql, codes):
    with pytest.raises(SQLRejected) as info:
        V.validate(sql)
    assert info.value.code in codes, (
        f"{case_id}: rejected for {info.value.code}: {info.value.message}"
    )


def test_adversarial_suite_has_at_least_60_cases():
    assert len(ADVERSARIAL) >= 60
    assert len({c[0] for c in ADVERSARIAL}) == len(ADVERSARIAL)


@pytest.mark.parametrize("sql", ALLOWED)
def test_ordinary_analytical_sql_is_allowed(sql):
    result = V.validate(sql)
    assert result.sql.upper().startswith(("SELECT", "WITH"))


def test_executed_sql_is_regenerated_without_comments():
    result = V.validate("SELECT store_id /* note */ FROM analytics.dim_store -- end")
    assert "/*" not in result.sql and "--" not in result.sql
    assert result.columns == {("dim_store", "store_id")}


def test_star_expands_to_documented_columns():
    result = V.validate("SELECT * FROM analytics.dim_customer")
    assert result.columns == {
        ("dim_customer", c.name) for c in DICTIONARY.view("dim_customer").columns
    }


def test_columns_flagged_as_personal_data_are_rejected_even_if_documented():
    """A masked or PII column added to the dictionary later must still be unqueryable."""
    view = DICTIONARY.view("dim_customer")
    pii_col = Column(
        name="phone_masked", type="text", description="Masked phone number, PII.", pii=True
    )
    views = [
        v.model_copy(update={"columns": [*v.columns, pii_col]}) if v.name == view.name else v
        for v in DICTIONARY.views
    ]
    validator = SQLValidator(
        Dictionary.model_validate(
            DICTIONARY.model_dump(by_alias=True)
            | {"views": [v.model_dump(by_alias=True) for v in views]}
        )
    )
    for sql in (
        "SELECT phone_masked FROM analytics.dim_customer",
        "SELECT * FROM analytics.dim_customer",
        "SELECT x.phone_masked FROM (SELECT * FROM analytics.dim_customer) x",
        "WITH c AS (SELECT phone_masked AS p FROM analytics.dim_customer) SELECT p FROM c",
    ):
        with pytest.raises(SQLRejected) as info:
            validator.validate(sql)
        assert info.value.code == "pii_column", sql
