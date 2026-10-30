"""Create the API's schema and login, and seed the demo users: `uv run poe app-setup`.

Idempotent: tables are created if missing, stored runs are kept, and the demo users'
passwords and scopes are reset to the values in `.env` and `sql_analyst.users`.
"""

import sys
from pathlib import Path

import psycopg
from argon2 import PasswordHasher
from psycopg import sql

from sql_analyst.config import WRITER_ROLE, Settings, get_settings
from sql_analyst.users import DEMO_USERS

APP_SQL = Path(__file__).with_name("app.sql")

DISPLAY_NAMES = {"analyst": "Demo analyst", "manager_jakarta": "Demo manager (Jakarta)"}


def ensure_writer_role(conn: psycopg.Connection, password: str) -> None:
    if len(password) < 16:
        raise ValueError("APP_WRITER_PASSWORD must be set (at least 16 characters)")
    role = sql.Identifier(WRITER_ROLE)
    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (WRITER_ROLE,)).fetchone():
        conn.execute(sql.SQL("CREATE ROLE {}").format(role))
    conn.execute(
        sql.SQL(
            "ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
        ).format(role)
    )
    conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(role, sql.Literal(password)))
    conn.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5s'").format(role))
    conn.execute(sql.SQL("ALTER ROLE {} SET search_path = app").format(role))
    conn.execute(sql.SQL("ALTER ROLE {} CONNECTION LIMIT 10").format(role))
    conn.execute(
        sql.SQL("REVOKE TEMPORARY ON DATABASE {} FROM {}").format(
            sql.Identifier(conn.info.dbname), role
        )
    )


def demo_passwords(settings: Settings) -> dict[str, str]:
    passwords = {
        "analyst": settings.demo_analyst_password.get_secret_value(),
        "manager_jakarta": settings.demo_manager_password.get_secret_value(),
    }
    for key, value in passwords.items():
        if len(value) < 8:
            raise ValueError(f"The demo password for {key} must be set (at least 8 characters)")
    return passwords


def setup_app(settings: Settings) -> list[str]:
    hasher = PasswordHasher()
    passwords = demo_passwords(settings)
    with psycopg.connect(settings.admin_conninfo()) as conn, conn.transaction():
        ensure_writer_role(conn, settings.app_writer_password.get_secret_value())
        conn.execute(APP_SQL.read_text(encoding="utf-8"))
        for key, scope in DEMO_USERS.items():
            regions = None if scope.region_ids == "all" else list(scope.region_ids)
            conn.execute(
                "INSERT INTO app.users (user_id, display_name, password_hash, role, region_ids) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET "
                "display_name = EXCLUDED.display_name, password_hash = EXCLUDED.password_hash, "
                "role = EXCLUDED.role, region_ids = EXCLUDED.region_ids",
                (
                    scope.user_id,
                    DISPLAY_NAMES[key],
                    hasher.hash(passwords[key]),
                    scope.role,
                    regions,
                ),
            )
    return [s.user_id for s in DEMO_USERS.values()]


def main() -> int:
    users = setup_app(get_settings())
    print(f"app-setup OK: schema app, role {WRITER_ROLE}, demo users {', '.join(users)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
