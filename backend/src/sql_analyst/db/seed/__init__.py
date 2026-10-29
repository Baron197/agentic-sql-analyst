"""Deterministic synthetic data for PT Arunika Niaga (fictional).

`generate(seed=42)` returns every core table in memory. The same seed, scale, and
locked dependency versions (Python 3.12, Faker in uv.lock) always give identical rows.
`scale` shrinks the volume tables for fast tests; the default is the full dataset.
"""

from sql_analyst.db.calendar import CALENDAR_COLUMNS, calendar_rows
from sql_analyst.db.seed import catalog, ops, reference
from sql_analyst.db.seed.common import Table
from sql_analyst.db.seed.sales import generate_sales

SEED = 42
N_CUSTOMERS = 20_000


def generate(seed: int = SEED, scale: float = 1.0) -> list[Table]:
    """All core tables in load order (parents before children)."""
    store_rows = reference.stores()
    promo_rows = reference.promotions()
    supplier_rows = catalog.suppliers(seed)
    product_rows, products = catalog.products(seed)
    customer_rows, customers = catalog.customers(seed, round(N_CUSTOMERS * scale))
    employee_rows, employees = catalog.employees(seed, store_rows)
    sales = generate_sales(seed, scale, store_rows, products, customers, employees, promo_rows)

    tables = [
        Table("calendar", CALENDAR_COLUMNS, calendar_rows()),
        Table(
            "regions",
            "region_id city province region_group island city_code",
            list(reference.REGIONS),
        ),
        Table(
            "channels",
            "channel_id channel_code channel_name is_online",
            list(reference.CHANNELS),
        ),
        Table(
            "stores",
            "store_id store_code store_name region_id store_format floor_area_m2 opened_date closed_date",
            store_rows,
        ),
        Table(
            "categories",
            "category_id parent_category_id category_name category_name_id level",
            catalog.categories(),
        ),
        Table(
            "suppliers",
            "supplier_id supplier_name region_id lead_time_days contact_name contact_email contact_phone",
            supplier_rows,
        ),
        Table(
            "products",
            "product_id sku product_name brand category_id supplier_id unit_cost_idr list_price_idr launched_date is_active",
            product_rows,
        ),
        Table(
            "customers",
            "customer_id full_name email phone address birth_date gender region_id segment signup_date",
            customer_rows,
        ),
        Table(
            "employees",
            "employee_id employee_code full_name email phone store_id job_role hire_date termination_date monthly_salary_idr",
            employee_rows,
        ),
        Table(
            "promotions",
            "promotion_id promo_code promo_name promo_type discount_pct channel_scope start_date end_date",
            promo_rows,
        ),
        *sales.tables,
        ops.inventory(seed, scale, store_rows, products),
        ops.purchase_orders(seed, scale, store_rows, products, supplier_rows),
        ops.sales_targets(seed, store_rows, sales.store_month_net),
        ops.store_traffic(seed, store_rows, sales.store_day_lambda),
        ops.support_tickets(seed, scale, sales.online_orders, customers, employees),
    ]
    return tables
