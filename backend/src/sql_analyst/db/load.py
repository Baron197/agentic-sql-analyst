"""Rebuild the `core` and `analytics` schemas and load the deterministic seed.

Run with `uv run poe db-load` (any database `.env` points at) or `uv run poe db-reset`
(start the local container first). Destroys and recreates both schemas.
"""

import sys
import time
from collections.abc import Callable
from pathlib import Path

import psycopg

from sql_analyst.config import get_settings
from sql_analyst.db.seed import SEED, generate

SQL_DIR = Path(__file__).parent


def run_sql_file(conn: psycopg.Connection, name: str) -> None:
    conn.execute((SQL_DIR / name).read_text(encoding="utf-8"))


def load(
    conninfo: str,
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
    step("committed (views created)")
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("ANALYZE")
    step("analyzed")
    return {t.name: len(t.rows) for t in tables}


def main() -> int:
    settings = get_settings()
    started = time.perf_counter()
    try:
        counts = load(settings.admin_conninfo(), log=print)
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
