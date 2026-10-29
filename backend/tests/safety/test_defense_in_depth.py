"""Defense in depth: each read-only layer blocks writes on its own, and the database
enforces the region scope even when the SQL validator is bypassed.

Layers for writes: (1) SQL validator, (2) READ ONLY transaction, (3) the nlq_reader
role's privileges. Each test below disables the others and shows one layer holding.
"""

import psycopg
import pytest
from psycopg import errors as pg_errors

from sql_analyst.dictionary.loader import load_dictionary
from sql_analyst.safety.errors import SQLRejected
from sql_analyst.safety.scope import apply_scope
from sql_analyst.safety.validator import SQLValidator

from .conftest import ANALYST, MANAGER

pytestmark = pytest.mark.db

WRITES = [
    "DELETE FROM analytics.fact_orders",
    "UPDATE analytics.fact_orders SET total_amount = 0",
    "INSERT INTO analytics.dim_channel VALUES (9, 'x', 'x', true)",
    "TRUNCATE analytics.fact_orders",
    "DROP VIEW analytics.fact_orders",
    "CREATE TABLE analytics.stolen (id int)",
    "CREATE TEMP TABLE stolen AS SELECT 1 AS x",
    "ALTER TABLE core.orders DISABLE ROW LEVEL SECURITY",
]
DENIED_ERRORS = (pg_errors.InsufficientPrivilege, pg_errors.ReadOnlySqlTransaction)


@pytest.mark.parametrize("sql", WRITES)
def test_delete_sent_straight_to_the_database_is_refused(reader_conn, settings, sql):
    """Guide §7: bypass the validator and send writes straight to the executor's role."""
    apply_scope(reader_conn, ANALYST, settings.signing_key())
    with pytest.raises(DENIED_ERRORS):
        reader_conn.execute(sql)
    reader_conn.rollback()
    with psycopg.connect(settings.admin_conninfo()) as admin:
        assert admin.execute("SELECT count(*) FROM core.orders").fetchone()[0] == 60046


@pytest.mark.parametrize("sql", WRITES)
def test_layer_validator_alone_rejects_writes(sql):
    with pytest.raises(SQLRejected):
        SQLValidator(load_dictionary()).validate(sql)


def test_layer_read_only_transaction_alone_blocks_even_the_superuser(settings):
    """No validator and a role that may write: the READ ONLY transaction still refuses."""
    with psycopg.connect(settings.admin_conninfo(), autocommit=True) as conn:
        conn.execute("BEGIN READ ONLY")
        with pytest.raises(pg_errors.ReadOnlySqlTransaction):
            conn.execute("DELETE FROM core.orders WHERE order_id = 1")
        conn.execute("ROLLBACK")


def test_layer_role_privileges_alone_block_writes_in_a_read_write_transaction(settings):
    """No validator and a READ WRITE transaction: the role has no write privilege."""
    with psycopg.connect(settings.reader_conninfo(), autocommit=True) as conn:
        conn.execute("BEGIN READ WRITE")
        assert (
            conn.execute("SELECT current_setting('transaction_read_only')").fetchone()[0] == "off"
        )
        for sql in ("DELETE FROM analytics.fact_orders", "UPDATE analytics.dim_store SET store_name = 'x'",
                    "CREATE TABLE analytics.stolen (id int)", "CREATE TEMP TABLE stolen (id int)",
                    "ALTER ROLE nlq_reader BYPASSRLS", "GRANT SELECT ON core.customers TO nlq_reader"):  # fmt: skip
            with pytest.raises(pg_errors.InsufficientPrivilege):
                conn.execute(sql)
            conn.execute("ROLLBACK")
            conn.execute("BEGIN READ WRITE")
        conn.execute("ROLLBACK")


def test_manager_hand_written_sql_against_another_region_returns_zero_rows(
    executor, reader_conn, settings
):
    """Guide §7: the manager's own SQL, with and without the validator, sees no Surabaya rows."""
    sql = (
        "SELECT count(*) FROM analytics.fact_orders o "
        "JOIN analytics.dim_store s ON s.store_id = o.store_id WHERE s.region_id = 9"
    )
    assert executor.run(sql, ANALYST).rows[0][0] > 0  # the rows exist
    assert executor.run(sql, MANAGER).rows == [[0]]  # full path
    apply_scope(reader_conn, MANAGER, settings.signing_key())  # validator bypassed
    assert reader_conn.execute(sql).fetchone()[0] == 0
    reader_conn.execute("SELECT set_config('app.region_ids', 'all', true)")  # and tampering
    assert reader_conn.execute(sql).fetchone()[0] == 0


@pytest.mark.parametrize(
    ("sql", "error"),
    [
        ("SELECT count(*) FROM core.customers", pg_errors.InsufficientPrivilege),
        ("SELECT key FROM rls.signing_key", pg_errors.InsufficientPrivilege),
        ("SELECT rls.verified_scope()", pg_errors.InsufficientPrivilege),
        ("SELECT pg_read_file('/etc/passwd')", pg_errors.InsufficientPrivilege),
        ("SELECT pg_ls_dir('/')", pg_errors.InsufficientPrivilege),
        ("SET ROLE postgres", pg_errors.InsufficientPrivilege),
        ("SET ROLE analytics_owner", pg_errors.InsufficientPrivilege),
        ("COPY (SELECT 1) TO '/tmp/x'", pg_errors.InsufficientPrivilege),
        ("ALTER ROLE nlq_reader BYPASSRLS", DENIED_ERRORS),  # read-only transaction refuses first
    ],
)
def test_reader_role_cannot_reach_core_secrets_files_or_other_roles(reader_conn, sql, error):
    with pytest.raises(error):
        reader_conn.execute(sql)


def test_reader_role_attributes(admin_conn):
    row = admin_conn.execute(
        "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolconfig FROM pg_roles WHERE rolname = 'nlq_reader'"
    ).fetchone()
    assert row[:4] == (False, False, False, False)
    assert "default_transaction_read_only=on" in row[4]
    owner = admin_conn.execute(
        "SELECT rolcanlogin, rolbypassrls FROM pg_roles WHERE rolname = 'analytics_owner'"
    ).fetchone()
    assert owner == (False, False)
