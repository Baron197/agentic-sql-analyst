-- core: raw tables for PT Arunika Niaga (fictional). Contains personal data.
-- The agent's database role never gets access to this schema (Phase 2).
-- Primary keys are created here; foreign keys and indexes are added after the
-- bulk load in constraints.sql, which also validates referential integrity.
-- All timestamps are timestamptz stored in UTC; business days are WIB (UTC+7).
-- All money is IDR as BIGINT (whole rupiah).

CREATE SCHEMA core;

CREATE TABLE core.calendar (
    date_key        date PRIMARY KEY,
    year            smallint NOT NULL,
    quarter         smallint NOT NULL,
    month           smallint NOT NULL,
    month_name      text NOT NULL,
    day_of_month    smallint NOT NULL,
    iso_day_of_week smallint NOT NULL,
    day_name        text NOT NULL,
    is_weekend      boolean NOT NULL,
    fiscal_year     smallint NOT NULL,
    fiscal_quarter  smallint NOT NULL,
    fiscal_month    smallint NOT NULL,
    is_ramadan      boolean NOT NULL,
    is_lebaran      boolean NOT NULL,
    is_harbolnas    boolean NOT NULL,
    holiday_name    text
);

CREATE TABLE core.regions (
    region_id    smallint PRIMARY KEY,
    city         text NOT NULL UNIQUE,
    province     text NOT NULL,
    region_group text NOT NULL,
    island       text NOT NULL,
    city_code    text NOT NULL UNIQUE
);

CREATE TABLE core.channels (
    channel_id   smallint PRIMARY KEY,
    channel_code text NOT NULL UNIQUE,
    channel_name text NOT NULL,
    is_online    boolean NOT NULL
);

CREATE TABLE core.stores (
    store_id     smallint PRIMARY KEY,
    store_code   text NOT NULL UNIQUE,
    store_name   text NOT NULL,
    region_id    smallint NOT NULL,
    store_format text NOT NULL,
    floor_area_m2 integer NOT NULL,
    opened_date  date NOT NULL,
    closed_date  date
);

CREATE TABLE core.categories (
    category_id        smallint PRIMARY KEY,
    parent_category_id smallint,
    category_name      text NOT NULL,
    category_name_id   text NOT NULL,
    level              smallint NOT NULL
);

CREATE TABLE core.suppliers (
    supplier_id    smallint PRIMARY KEY,
    supplier_name  text NOT NULL,
    region_id      smallint NOT NULL,
    lead_time_days smallint NOT NULL,
    contact_name   text NOT NULL,
    contact_email  text NOT NULL,
    contact_phone  text NOT NULL
);

CREATE TABLE core.products (
    product_id     integer PRIMARY KEY,
    sku            text NOT NULL UNIQUE,
    product_name   text NOT NULL,
    brand          text NOT NULL,
    category_id    smallint NOT NULL,
    supplier_id    smallint NOT NULL,
    unit_cost_idr  bigint NOT NULL,
    list_price_idr bigint NOT NULL,
    launched_date  date NOT NULL,
    is_active      boolean NOT NULL
);

CREATE TABLE core.customers (
    customer_id integer PRIMARY KEY,
    full_name   text NOT NULL,
    email       text NOT NULL,
    phone       text NOT NULL,
    address     text NOT NULL,
    birth_date  date NOT NULL,
    gender      text NOT NULL,
    region_id   smallint NOT NULL,
    segment     text NOT NULL,
    signup_date date NOT NULL
);

CREATE TABLE core.employees (
    employee_id        integer PRIMARY KEY,
    employee_code      text NOT NULL UNIQUE,
    full_name          text NOT NULL,
    email              text NOT NULL,
    phone              text NOT NULL,
    store_id           smallint,
    job_role           text NOT NULL,
    hire_date          date NOT NULL,
    termination_date   date,
    monthly_salary_idr bigint NOT NULL
);

CREATE TABLE core.promotions (
    promotion_id   smallint PRIMARY KEY,
    promo_code     text NOT NULL UNIQUE,
    promo_name     text NOT NULL,
    promo_type     text NOT NULL,
    discount_pct   smallint NOT NULL,
    channel_scope  text NOT NULL,
    start_date     date NOT NULL,
    end_date       date NOT NULL
);

CREATE TABLE core.orders (
    order_id          integer PRIMARY KEY,
    order_number      text NOT NULL UNIQUE,
    customer_id       integer,
    store_id          smallint NOT NULL,
    channel_id        smallint NOT NULL,
    sales_employee_id integer,
    ordered_at        timestamptz NOT NULL,
    status            text NOT NULL,
    total_amount      bigint NOT NULL,
    region_code       text
);

CREATE TABLE core.order_items (
    order_item_id  integer PRIMARY KEY,
    order_id       integer NOT NULL,
    line_number    smallint NOT NULL,
    product_id     integer NOT NULL,
    quantity       integer NOT NULL,
    unit_price_idr bigint NOT NULL,
    discount_idr   bigint NOT NULL
);

CREATE TABLE core.payments (
    payment_id     integer PRIMARY KEY,
    order_id       integer NOT NULL,
    payment_method text NOT NULL,
    payment_status text NOT NULL,
    amount_idr     bigint NOT NULL,
    paid_at        timestamptz
);

CREATE TABLE core.returns (
    return_id         integer PRIMARY KEY,
    order_item_id     integer NOT NULL,
    order_id          integer NOT NULL,
    returned_at       timestamptz NOT NULL,
    quantity          integer NOT NULL,
    reason            text NOT NULL,
    refund_amount_idr bigint NOT NULL
);

CREATE TABLE core.shipments (
    shipment_id      integer PRIMARY KEY,
    order_id         integer NOT NULL UNIQUE,
    courier          text NOT NULL,
    destination_region_id smallint NOT NULL,
    shipping_fee_idr bigint NOT NULL,
    shipped_at       timestamptz NOT NULL,
    delivered_at     timestamptz,
    shipment_status  text NOT NULL
);

CREATE TABLE core.inventory_daily (
    snapshot_date date NOT NULL,
    store_id      smallint NOT NULL,
    product_id    integer NOT NULL,
    on_hand_qty   integer NOT NULL,
    reorder_point integer NOT NULL,
    PRIMARY KEY (snapshot_date, store_id, product_id)
);

CREATE TABLE core.purchase_orders (
    purchase_order_id integer PRIMARY KEY,
    po_number         text NOT NULL UNIQUE,
    supplier_id       smallint NOT NULL,
    store_id          smallint NOT NULL,
    product_id        integer NOT NULL,
    ordered_date      date NOT NULL,
    expected_date     date NOT NULL,
    received_date     date,
    quantity          integer NOT NULL,
    unit_cost_idr     bigint NOT NULL,
    po_status         text NOT NULL
);

CREATE TABLE core.promotion_redemptions (
    redemption_id integer PRIMARY KEY,
    promotion_id  smallint NOT NULL,
    order_id      integer NOT NULL UNIQUE,
    discount_idr  bigint NOT NULL,
    redeemed_at   timestamptz NOT NULL
);

CREATE TABLE core.web_sessions (
    session_id       integer PRIMARY KEY,
    channel_id       smallint NOT NULL,
    customer_id      integer,
    started_at       timestamptz NOT NULL,
    device_type      text NOT NULL,
    traffic_source   text NOT NULL,
    viewed_product   boolean NOT NULL,
    added_to_cart    boolean NOT NULL,
    reached_checkout boolean NOT NULL,
    converted        boolean NOT NULL,
    order_id         integer UNIQUE
);

CREATE TABLE core.support_tickets (
    ticket_id        integer PRIMARY KEY,
    ticket_number    text NOT NULL UNIQUE,
    customer_id      integer NOT NULL,
    order_id         integer,
    assigned_employee_id integer,
    created_at       timestamptz NOT NULL,
    contact_channel  text NOT NULL,
    ticket_category  text NOT NULL,
    subject          text NOT NULL,
    ticket_status    text NOT NULL,
    resolved_at      timestamptz,
    csat_score       smallint
);

CREATE TABLE core.sales_targets (
    store_id                smallint NOT NULL,
    month_start             date NOT NULL,
    target_net_revenue_idr  bigint NOT NULL,
    PRIMARY KEY (store_id, month_start)
);

CREATE TABLE core.store_daily_traffic (
    store_id     smallint NOT NULL,
    traffic_date date NOT NULL,
    visitors     integer NOT NULL,
    PRIMARY KEY (store_id, traffic_date)
);
