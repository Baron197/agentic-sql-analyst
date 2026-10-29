"""Fingerprint the loaded data: one MD5 per core table plus a combined hash.

Two rebuilds with the same seed must print identical output. Rows are hashed
individually and the hashes sorted, so the result does not depend on physical
row order; the session time zone is pinned so timestamps render the same way.
"""

import hashlib
import sys

import psycopg

from sql_analyst.config import get_settings


def table_checksums(conn: psycopg.Connection) -> dict[str, str]:
    conn.execute("SET TimeZone = 'UTC'")
    conn.execute("SET DateStyle = 'ISO, YMD'")
    names = [
        r[0]
        for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'core' AND table_type = 'BASE TABLE' ORDER BY table_name"
        )
    ]
    out = {}
    for name in names:
        row = conn.execute(
            f"SELECT count(*), md5(coalesce(string_agg(h, '' ORDER BY h), '')) "
            f"FROM (SELECT md5(t::text) AS h FROM core.{name} t) s"
        ).fetchone()
        out[name] = f"{row[0]}:{row[1]}"
    return out


def combined(checksums: dict[str, str]) -> str:
    return hashlib.sha256(
        "\n".join(f"{k}={v}" for k, v in sorted(checksums.items())).encode()
    ).hexdigest()


def main() -> int:
    with psycopg.connect(get_settings().admin_conninfo()) as conn:
        sums = table_checksums(conn)
    for name, value in sums.items():
        print(f"  {name:<24} {value}")
    print(f"combined sha256: {combined(sums)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
