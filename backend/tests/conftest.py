"""Shared test setup.

Tests marked `db` need the Postgres container. Locally they are skipped when it
is down; with REQUIRE_DB=1 (set in CI) an unreachable database is a failure.
"""

import os

import psycopg
import pytest

from sql_analyst.config import get_settings


def _db_reachable() -> bool:
    try:
        with psycopg.connect(get_settings().admin_conninfo(), connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


def pytest_collection_modifyitems(config, items):
    db_items = [item for item in items if "db" in item.keywords]
    if not db_items or os.environ.get("REQUIRE_DB") == "1" or _db_reachable():
        return
    skip = pytest.mark.skip(reason="Postgres not reachable (run `uv run poe db-up`)")
    for item in db_items:
        item.add_marker(skip)
