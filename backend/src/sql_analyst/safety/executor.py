"""Executor (safety layers 3, 5, 6): run validated SQL as the read-only role.

For every query:
- connect as `nlq_reader` (SELECT on analytics views only) from a small pool;
- open a READ ONLY transaction with a statement timeout;
- set the signed region scope of the signed-in user (row-level security);
- check the planner cost (layer 4);
- run the SQL wrapped in an outer LIMIT (row cap, layer 3) and report truncation.
"""

import time
from typing import Any

import psycopg
from psycopg import errors as pg_errors
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from sql_analyst.config import Settings
from sql_analyst.dictionary.models import Dictionary
from sql_analyst.safety.cost_guard import check_cost
from sql_analyst.safety.errors import QueryFailed, QueryTimeout
from sql_analyst.safety.scope import UserScope, apply_scope
from sql_analyst.safety.validator import SQLValidator, ValidatedSQL


class QueryResult(BaseModel):
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    plan_cost: float
    elapsed_ms: float


def _configure(conn: psycopg.Connection) -> None:
    conn.read_only = True  # every transaction starts with BEGIN READ ONLY


class Executor:
    """Validate and run SQL for a user. Thread-safe; close() when done."""

    def __init__(
        self,
        validator: SQLValidator,
        conninfo: str,
        signing_key: bytes,
        *,
        row_limit: int = 1_000,
        timeout_ms: int = 5_000,
        cost_limit: float = 250_000.0,
        pool_size: int = 4,
    ):
        self.validator = validator
        self.signing_key = signing_key
        self.row_limit = row_limit
        self.timeout_ms = timeout_ms
        self.cost_limit = cost_limit
        self.pool = ConnectionPool(
            conninfo, min_size=1, max_size=pool_size, configure=_configure, open=True, timeout=10
        )

    @classmethod
    def from_settings(cls, settings: Settings, dictionary: Dictionary) -> "Executor":
        return cls(
            SQLValidator(dictionary),
            settings.reader_conninfo(),
            settings.signing_key(),
            row_limit=settings.query_row_limit,
            timeout_ms=settings.query_timeout_ms,
            cost_limit=settings.query_cost_limit,
        )

    def close(self) -> None:
        self.pool.close()

    def __enter__(self) -> "Executor":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def run(self, sql: str, scope: UserScope) -> QueryResult:
        """Validate, then execute. Raises a SafetyError subclass on any refusal or failure."""
        return self.run_validated(self.validator.validate(sql), scope)

    def run_validated(self, validated: ValidatedSQL, scope: UserScope) -> QueryResult:
        wrapped = f"SELECT * FROM ({validated.sql}) AS _q LIMIT {self.row_limit + 1}"
        started = time.perf_counter()
        try:
            with self.pool.connection() as conn, conn.transaction():
                conn.execute(f"SET LOCAL statement_timeout = {int(self.timeout_ms)}")
                conn.execute("SET LOCAL search_path = analytics")
                apply_scope(conn, scope, self.signing_key)
                cost = check_cost(conn, wrapped, self.cost_limit)
                cur = conn.execute(wrapped)
                columns = [d.name for d in cur.description or []]
                rows = [list(r) for r in cur.fetchall()]
        except pg_errors.QueryCanceled as e:
            raise QueryTimeout(
                f"The query took longer than {self.timeout_ms / 1000:g} s and was cancelled."
            ) from e
        except psycopg.Error as e:
            detail = e.diag.message_primary if e.diag and e.diag.message_primary else str(e)
            raise QueryFailed(f"The database rejected the query: {detail}") from e
        truncated = len(rows) > self.row_limit
        rows = rows[: self.row_limit]
        return QueryResult(
            sql=validated.sql,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            plan_cost=cost,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
        )
