"""Connect to Postgres and report the server version and pgvector availability.

Run with `uv run poe db-ping`. Exits non-zero if the database is unreachable or
the `vector` extension is missing from the image.
"""

import sys

import psycopg
from pydantic import BaseModel

from sql_analyst.config import Settings, get_settings


class PingResult(BaseModel):
    server_version: str
    vector_available: bool


def ping(settings: Settings, timeout_s: int = 5) -> PingResult:
    """Open one connection, read the version, and check that pgvector can be installed."""
    with psycopg.connect(settings.admin_conninfo(), connect_timeout=timeout_s) as conn:
        version = conn.execute("SHOW server_version").fetchone()
        vector = conn.execute(
            "SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"
        ).fetchone()
    return PingResult(server_version=version[0] if version else "?", vector_available=bool(vector))


def main() -> int:
    settings = get_settings()
    target = f"{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    try:
        result = ping(settings)
    except psycopg.OperationalError as exc:
        print(f"db-ping FAILED: cannot connect to {target}: {exc}", file=sys.stderr)
        return 1
    print(f"db-ping OK: {target}, PostgreSQL {result.server_version}")
    if not result.vector_available:
        print("db-ping FAILED: the 'vector' extension is not available", file=sys.stderr)
        return 1
    print("pgvector extension: available")
    return 0


if __name__ == "__main__":
    sys.exit(main())
