"""Phase 1 Definition of Done checks against the loaded database (`uv run poe db-reset`)."""

import psycopg
import pytest
from psycopg import sql

from sql_analyst.config import get_settings
from sql_analyst.db.load import SQL_DIR
from sql_analyst.db.seed.ops import INJECTION_SUBJECT
from sql_analyst.dictionary.loader import load_dictionary
from sql_analyst.dictionary.values import MAX_VALUES_PER_COLUMN, fetch_values
from sql_analyst.safety.scope import UserScope, apply_scope

pytestmark = pytest.mark.db

D = load_dictionary()

# Expected row counts for the full seed (scale 1.0): (min, max).
EXPECTED_ROWS = {
    "calendar": (1186, 1186),
    "regions": (12, 12),
    "channels": (4, 4),
    "stores": (40, 40),
    "categories": (20, 30),
    "suppliers": (20, 30),
    "products": (200, 300),
    "customers": (20_000, 20_000),
    "employees": (350, 500),
    "promotions": (45, 60),
    "orders": (55_000, 65_000),
    "order_items": (130_000, 170_000),
    "payments": (55_000, 65_000),
    "returns": (4_000, 9_000),
    "shipments": (20_000, 32_000),
    "promotion_redemptions": (5_000, 12_000),
    "web_sessions": (180_000, 320_000),
    "inventory_daily": (700_000, 1_100_000),
    "purchase_orders": (3_000, 5_000),
    "sales_targets": (1_300, 1_700),
    "store_daily_traffic": (35_000, 42_000),
    "support_tickets": (5_000, 9_000),
}
PII_COLUMNS = {
    "full_name", "email", "phone", "address", "birth_date", "gender", "monthly_salary_idr",
    "contact_name", "contact_email", "contact_phone",
}  # fmt: skip
TYPE_ALIASES = {"timestamptz": "timestamp with time zone"}


@pytest.fixture(scope="module")
def conn():
    """Admin connection with the signed all-regions scope: the analytics views are
    row-level secured (Phase 2), so without a scope even the admin sees zero rows.
    All tests share one transaction, which the signature is bound to."""
    settings = get_settings()
    with psycopg.connect(settings.admin_conninfo()) as c:
        c.execute("SET TimeZone = 'UTC'")
        apply_scope(
            c, UserScope(user_id="tests", role="analyst", region_ids="all"), settings.signing_key()
        )
        assert c.execute("SELECT count(*) FROM analytics.fact_orders").fetchone()[0] > 0
        yield c


def _scalar(conn, query, params=None):
    return conn.execute(query, params).fetchone()[0]


def test_row_counts_in_expected_ranges(conn):
    for table, (lo, hi) in EXPECTED_ROWS.items():
        n = _scalar(conn, sql.SQL("SELECT count(*) FROM core.{}").format(sql.Identifier(table)))
        assert lo <= n <= hi, f"core.{table}: {n} not in [{lo}, {hi}]"


def test_every_declared_foreign_key_exists_and_is_validated(conn):
    declared = (SQL_DIR / "constraints.sql").read_text(encoding="utf-8").count("FOREIGN KEY")
    n = _scalar(
        conn,
        "SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace "
        "WHERE n.nspname = 'core' AND c.contype = 'f' AND c.convalidated",
    )
    assert declared >= 30
    assert n == declared


def test_no_orphans_along_any_join_path(conn):
    for jp in D.join_paths:
        fv, fc = jp.from_.split(".")
        tv, tc = jp.to.split(".")
        orphans = _scalar(
            conn,
            sql.SQL(
                "SELECT count(*) FROM analytics.{fv} f WHERE f.{fc} IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM analytics.{tv} t WHERE t.{tc} = f.{fc})"
            ).format(
                fv=sql.Identifier(fv),
                fc=sql.Identifier(fc),
                tv=sql.Identifier(tv),
                tc=sql.Identifier(tc),
            ),
        )
        assert orphans == 0, f"{jp.from_} -> {jp.to}: {orphans} orphans"


def test_dictionary_matches_analytics_columns_exactly(conn):
    rows = conn.execute(
        "SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod) "
        "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'analytics' AND a.attnum > 0 AND NOT a.attisdropped"
    ).fetchall()
    in_db = {(view, col): typ for view, col, typ in rows}
    documented = {
        (v.name, c.name): TYPE_ALIASES.get(c.type, c.type) for v in D.views for c in v.columns
    }
    assert set(in_db) - set(documented) == set(), "undocumented analytics columns"
    assert set(documented) - set(in_db) == set(), "documented columns missing from the database"
    mismatched = {k: (documented[k], in_db[k]) for k in in_db if documented[k] != in_db[k]}
    assert mismatched == {}


def test_every_analytics_column_is_described():
    columns = [c for v in D.views for c in v.columns]
    assert all(len(c.description) >= 10 for c in columns)


def test_every_glossary_sql_runs_and_returns_a_value(conn):
    for metric in D.glossary:
        rows = conn.execute(metric.sql).fetchall()
        assert len(rows) == 1 and rows[0][0] is not None, metric.name
        assert rows[0][0] > 0, metric.name


def test_glossary_ratios_are_plausible(conn):
    values = {m.name: conn.execute(m.sql).fetchone()[0] for m in D.glossary}
    assert values["gross_sales"] > values["net_revenue"]
    assert 0.01 < values["return_rate"] < 0.10
    assert 0.03 < values["conversion_rate"] < 0.15


def test_no_personal_data_in_analytics(conn):
    cols = {
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'analytics'"
        )
    }
    assert cols & PII_COLUMNS == set()


def test_planted_injection_row_is_present_once(conn):
    n = _scalar(
        conn,
        "SELECT count(*) FROM analytics.fact_support_tickets WHERE subject = %s",
        (INJECTION_SUBJECT,),
    )
    assert n == 1


def test_traps_are_present(conn):
    after = _scalar(
        conn,
        "SELECT count(*) FROM analytics.fact_orders WHERE ordered_at >= '2025-07-01 00:00+07' AND region_code IS NOT NULL",
    )
    assert after == 0, "region_code must be NULL after deprecation"
    stale = _scalar(
        conn,
        "SELECT count(*) FROM analytics.fact_orders o JOIN analytics.dim_customer c USING (customer_id) "
        "JOIN analytics.dim_region r ON r.region_id = c.region_id "
        "WHERE o.region_code IS NOT NULL AND o.region_code <> r.city_code",
    )
    assert stale > 0, "some region_code values must be stale"
    cross_midnight = _scalar(
        conn,
        "SELECT count(*) FROM analytics.fact_orders "
        "WHERE (ordered_at AT TIME ZONE 'UTC')::date <> (ordered_at AT TIME ZONE 'Asia/Jakarta')::date",
    )
    assert cross_midnight > 1000, "UTC and WIB dates must differ for late-night orders"


def test_value_index_source_covers_every_categorical_column(conn):
    values = fetch_values(conn, D)
    by_column: dict[tuple[str, str], set[str]] = {}
    for v in values:
        by_column.setdefault((v.view, v.column), set()).add(v.value)
    for view, column in D.categorical_columns():
        found = by_column.get((view, column), set())
        assert found, f"{view}.{column} has no values"
        assert len(found) <= MAX_VALUES_PER_COLUMN, f"{view}.{column} is not categorical"
        examples = set(D.view(view).column(column).examples)
        assert examples <= found, f"{view}.{column} examples not in data: {examples - found}"
