"""Safety layer 6: row-level security keyed on the signed region scope."""

import psycopg
import pytest

from sql_analyst.safety.scope import UserScope, apply_scope

from .conftest import ANALYST, JABODETABEK, MANAGER

pytestmark = pytest.mark.db

ORDERS_BY_REGION = (
    "SELECT s.region_id, count(*) FROM analytics.fact_orders o "
    "JOIN analytics.dim_store s ON s.store_id = o.store_id GROUP BY 1"
)

# Region-scoped views and how to find the region of each row.
REGION_OF_ROWS = {
    "dim_store": "SELECT DISTINCT region_id FROM analytics.dim_store",
    "dim_customer": "SELECT DISTINCT region_id FROM analytics.dim_customer",
    "fact_orders": "SELECT DISTINCT s.region_id FROM analytics.fact_orders x JOIN analytics.dim_store s USING (store_id)",
    "fact_inventory_daily": "SELECT DISTINCT s.region_id FROM analytics.fact_inventory_daily x JOIN analytics.dim_store s USING (store_id)",
    "fact_purchase_orders": "SELECT DISTINCT s.region_id FROM analytics.fact_purchase_orders x JOIN analytics.dim_store s USING (store_id)",
    "fact_sales_targets": "SELECT DISTINCT s.region_id FROM analytics.fact_sales_targets x JOIN analytics.dim_store s USING (store_id)",
    "fact_store_daily_traffic": "SELECT DISTINCT s.region_id FROM analytics.fact_store_daily_traffic x JOIN analytics.dim_store s USING (store_id)",
    "dim_employee": "SELECT DISTINCT s.region_id FROM analytics.dim_employee x JOIN analytics.dim_store s USING (store_id)",
    "fact_support_tickets": "SELECT DISTINCT c.region_id FROM analytics.fact_support_tickets x JOIN analytics.dim_customer c USING (customer_id)",
}
# Views whose rows hang off an order: every visible row must belong to a visible order.
ORDER_CHILDREN = [
    "fact_order_items",
    "fact_payments",
    "fact_returns",
    "fact_shipments",
    "fact_promotion_redemptions",
]

# Hand-written attempts by the Jakarta manager to read Surabaya (region 9).
CROSS_REGION_ATTEMPTS = [
    "SELECT count(*) FROM analytics.fact_orders o JOIN analytics.dim_store s ON s.store_id = o.store_id WHERE s.region_id = 9",
    "SELECT count(*) FROM analytics.fact_orders WHERE store_id IN (SELECT store_id FROM analytics.dim_store WHERE region_id = 9)",
    "WITH sby AS (SELECT store_id FROM analytics.dim_store WHERE region_id = 9) SELECT count(*) FROM analytics.fact_orders o JOIN sby USING (store_id)",
    "SELECT count(*) FROM (SELECT order_id FROM analytics.fact_orders WHERE store_id = 30 UNION ALL SELECT order_id FROM analytics.fact_orders WHERE store_id = 31) u",
    "SELECT count(*) FROM analytics.fact_order_items oi WHERE oi.order_id IN (SELECT order_id FROM analytics.fact_orders WHERE store_id BETWEEN 30 AND 34)",
    "SELECT count(*) FROM analytics.fact_inventory_daily WHERE store_id = 30",
    "SELECT count(*) FROM analytics.dim_customer WHERE region_id = 9",
    "SELECT count(*) FROM analytics.fact_support_tickets t JOIN analytics.dim_customer c USING (customer_id) WHERE c.region_id = 9",
    "SELECT count(*) FROM analytics.fact_shipments WHERE destination_region_id = 9",
    "SELECT count(*) FROM analytics.dim_store WHERE store_name ILIKE '%Surabaya%'",
]


def test_analyst_sees_every_region(executor):
    regions = {r[0] for r in executor.run(ORDERS_BY_REGION, ANALYST).rows}
    assert regions == set(range(1, 13))


def test_manager_sees_only_jabodetabek_orders(executor):
    regions = {r[0] for r in executor.run(ORDERS_BY_REGION, MANAGER).rows}
    assert regions == set(JABODETABEK)


@pytest.mark.parametrize("view", list(REGION_OF_ROWS))
def test_manager_rows_stay_in_scope_in_every_scoped_view(executor, view):
    regions = {r[0] for r in executor.run(REGION_OF_ROWS[view], MANAGER).rows}
    assert regions and regions <= set(JABODETABEK), f"{view}: {regions}"


@pytest.mark.parametrize("view", ORDER_CHILDREN)
def test_manager_order_child_rows_belong_to_visible_orders(executor, view):
    orphans = executor.run(
        f"SELECT count(*) FROM analytics.{view} x "
        "WHERE NOT EXISTS (SELECT 1 FROM analytics.fact_orders o WHERE o.order_id = x.order_id)",
        MANAGER,
    ).rows[0][0]
    total = executor.run(f"SELECT count(*) FROM analytics.{view}", MANAGER).rows[0][0]
    analyst_total = executor.run(f"SELECT count(*) FROM analytics.{view}", ANALYST).rows[0][0]
    assert orphans == 0 and 0 < total < analyst_total


@pytest.mark.parametrize("sql", CROSS_REGION_ATTEMPTS)
def test_manager_cross_region_attempts_return_zero_rows(executor, sql):
    assert executor.run(sql, MANAGER).rows == [[0]]


def test_reference_data_is_not_region_scoped(executor):
    for view, n in (("dim_region", 12), ("dim_product", 251), ("dim_channel", 4)):
        assert executor.run(f"SELECT count(*) FROM analytics.{view}", MANAGER).rows == [[n]]


def _orders_seen(conn: psycopg.Connection, setup: list[tuple[str, tuple]] | None = None) -> int:
    for stmt, params in setup or []:
        conn.execute(stmt, params)
    return conn.execute("SELECT count(*) FROM analytics.fact_orders").fetchone()[0]


def test_no_scope_means_zero_rows(reader_conn):
    assert _orders_seen(reader_conn) == 0


def test_superuser_reading_the_views_without_scope_sees_zero_rows(admin_conn):
    """The views' owner is subject to RLS, so even the admin role needs a signed scope."""
    assert _orders_seen(admin_conn) == 0


@pytest.mark.parametrize(
    "forgery",
    [
        [("SELECT set_config('app.region_ids', 'all', true)", ())],
        [
            (
                "SELECT set_config('app.region_ids', 'all', true), set_config('app.region_sig', %s, true)",
                ("0" * 64,),
            )
        ],
        [("SELECT set_config('app.region_ids', '1,2,3,4,5,6,7,8,9,10,11,12', false)", ())],
    ],
    ids=["ids_only", "random_signature", "session_level_list"],
)
def test_forged_scope_without_valid_signature_sees_zero_rows(reader_conn, forgery):
    assert _orders_seen(reader_conn, forgery) == 0


def test_valid_manager_signature_cannot_be_reused_for_other_regions(reader_conn, settings):
    apply_scope(reader_conn, MANAGER, settings.signing_key())
    assert _orders_seen(reader_conn) > 0
    widened = [("SELECT set_config('app.region_ids', 'all', true)", ())]
    assert _orders_seen(reader_conn, widened) == 0


def test_signature_is_bound_to_its_transaction(reader_conn, settings):
    apply_scope(reader_conn, ANALYST, settings.signing_key())
    ids, sig = reader_conn.execute(
        "SELECT current_setting('app.region_ids'), current_setting('app.region_sig')"
    ).fetchone()
    assert _orders_seen(reader_conn) == 60046
    reader_conn.commit()  # new transaction: replay the captured scope and signature
    replay = [
        (
            "SELECT set_config('app.region_ids', %s, true), set_config('app.region_sig', %s, true)",
            (ids, sig),
        )
    ]
    assert _orders_seen(reader_conn, replay) == 0


def test_scope_rejects_an_empty_region_list():
    with pytest.raises(ValueError):
        UserScope(user_id="x", role="manager", region_ids=[])
