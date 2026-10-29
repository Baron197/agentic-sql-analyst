"""Rebuild the `core`, `analytics`, and `rls` schemas, load the seed, apply the safety layer.

Run with `uv run poe db-load` (any database `.env` points at) or `uv run poe db-reset`
(start the local container first). Destroys and recreates the three schemas; the
cluster-level roles nlq_reader and analytics_owner are created once and updated.
"""

import sys
import time
from collections.abc import Callable
from pathlib import Path

import psycopg
from psycopg import sql

from sql_analyst.config import READER_ROLE, get_settings
from sql_analyst.db.seed import SEED, generate

SQL_DIR = Path(__file__).parent


def run_sql_file(conn: psycopg.Connection, name: str) -> None:
    conn.execute((SQL_DIR / name).read_text(encoding="utf-8"))


def ensure_roles(conn: psycopg.Connection, reader_password: str) -> None:
    """Create or update the agent's read-only login and the views' owner role."""
    if len(reader_password) < 16:
        raise ValueError("NLQ_READER_PASSWORD must be set (at least 16 characters)")
    for role, login in ((READER_ROLE, True), ("analytics_owner", False)):
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(role)))
        attrs = "LOGIN" if login else "NOLOGIN"
        conn.execute(
            sql.SQL(
                "ALTER ROLE {} "
                + attrs
                + " NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
            ).format(sql.Identifier(role))
        )
    reader = sql.Identifier(READER_ROLE)
    conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(reader, sql.Literal(reader_password)))
    conn.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(reader))
    conn.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5s'").format(reader))
    conn.execute(sql.SQL("ALTER ROLE {} SET search_path = analytics").format(reader))
    conn.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 20").format(reader))
    dbname = sql.Identifier(conn.info.dbname)
    conn.execute(sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC").format(dbname))
    conn.execute(sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM {}").format(dbname, reader))


def load(
    conninfo: str,
    reader_password: str,
    signing_key: bytes,
    seed: int = SEED,
    scale: float = 1.0,
    log: Callable[[str], None] = lambda _msg: None,
) -> dict[str, int]:
    """Drop and rebuild everything in one transaction. Returns row counts per core table."""
    t0 = time.perf_counter()

    def step(msg: str) -> None:
        log(f"[{time.perf_counter() - t0:6.1f}s] {msg}")

    tables = generate(seed=seed, scale=scale)
    step(f"generated {sum(len(t.rows) for t in tables):,} rows")
    with psycopg.connect(conninfo) as conn:
        conn.execute("SET TimeZone = 'UTC'")
        conn.execute("DROP SCHEMA IF EXISTS analytics CASCADE")
        conn.execute("DROP SCHEMA IF EXISTS rls CASCADE")
        conn.execute("DROP SCHEMA IF EXISTS core CASCADE")
        run_sql_file(conn, "schema.sql")
        step("schemas dropped and recreated")
        with conn.cursor() as cur:
            for table in tables:
                columns = ", ".join(table.columns)
                with cur.copy(f"COPY core.{table.name} ({columns}) FROM STDIN") as copy:
                    for row in table.rows:
                        copy.write_row(row)
        step("rows copied")
        run_sql_file(conn, "constraints.sql")
        step("foreign keys validated, indexes built")
        run_sql_file(conn, "views.sql")
        ensure_roles(conn, reader_password)
        run_sql_file(conn, "security.sql")
        conn.execute("INSERT INTO rls.signing_key (key) VALUES (%s)", (signing_key,))
    step("committed (views, roles, row-level security)")
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("ANALYZE")
    step("analyzed")
    return {t.name: len(t.rows) for t in tables}


def main() -> int:
    settings = get_settings()
    started = time.perf_counter()
    try:
        counts = load(
            settings.admin_conninfo(),
            settings.nlq_reader_password.get_secret_value(),
            settings.signing_key(),
            log=print,
        )
    except psycopg.OperationalError as exc:
        print(f"db-load FAILED: cannot connect: {exc}", file=sys.stderr)
        return 1
    for name, n in counts.items():
        print(f"  core.{name:<24} {n:>10,}")
    print(
        f"db-load OK: {sum(counts.values()):,} rows in {len(counts)} tables, "
        f"{time.perf_counter() - started:.1f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
