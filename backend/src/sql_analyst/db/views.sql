-- analytics: the only schema the agent can read (Phase 2 grants it to a read-only role).
-- Personal data (names, emails, phones, addresses, birth dates, salaries) is left out.
-- Every column here must be described in data/dictionary.yaml (enforced by a test).

CREATE SCHEMA analytics;

-- Calendar and places ------------------------------------------------------

CREATE VIEW analytics.dim_date AS
SELECT date_key, year, quarter, month, month_name, day_of_month, iso_day_of_week,
       day_name, is_weekend, fiscal_year, fiscal_quarter, fiscal_month,
       is_ramadan, is_lebaran, is_harbolnas, holiday_name
FROM core.calendar;

CREATE VIEW analytics.dim_region AS
SELECT region_id, city, province, region_group, island, city_code
FROM core.regions;

CREATE VIEW analytics.dim_store AS
SELECT store_id, store_code, store_name, region_id, store_format, floor_area_m2,
       opened_date, closed_date, (closed_date IS NULL) AS is_open
FROM core.stores;

CREATE VIEW analytics.dim_channel AS
SELECT channel_id, channel_code, channel_name, is_online
FROM core.channels;

-- Products -----------------------------------------------------------------

CREATE VIEW analytics.dim_category AS
SELECT category_id, parent_category_id, category_name, category_name_id, level
FROM core.categories;

CREATE VIEW analytics.dim_product AS
SELECT product_id, sku, product_name, brand, category_id, supplier_id,
       unit_cost_idr, list_price_idr, launched_date, is_active
FROM core.products;

CREATE VIEW analytics.dim_supplier AS
SELECT supplier_id, supplier_name, region_id, lead_time_days
FROM core.suppliers;

-- Customers (no name, email, phone, address, or birth date) ----------------

CREATE VIEW analytics.dim_customer AS
SELECT customer_id, segment, region_id, signup_date
FROM core.customers;

-- Sales --------------------------------------------------------------------

CREATE VIEW analytics.fact_orders AS
SELECT order_id, order_number, customer_id, store_id, channel_id, sales_employee_id,
       ordered_at, status, total_amount, region_code
FROM core.orders;

CREATE VIEW analytics.fact_order_items AS
SELECT order_item_id, order_id, line_number, product_id, quantity,
       unit_price_idr, discount_idr
FROM core.order_items;

CREATE VIEW analytics.fact_payments AS
SELECT payment_id, order_id, payment_method, payment_status, amount_idr, paid_at
FROM core.payments;

CREATE VIEW analytics.fact_returns AS
SELECT return_id, order_item_id, order_id, returned_at, quantity, reason, refund_amount_idr
FROM core.returns;

CREATE VIEW analytics.fact_shipments AS
SELECT shipment_id, order_id, courier, destination_region_id, shipping_fee_idr,
       shipped_at, delivered_at, shipment_status
FROM core.shipments;

-- Supply -------------------------------------------------------------------

CREATE VIEW analytics.fact_inventory_daily AS
SELECT snapshot_date, store_id, product_id, on_hand_qty, reorder_point
FROM core.inventory_daily;

CREATE VIEW analytics.fact_purchase_orders AS
SELECT purchase_order_id, po_number, supplier_id, store_id, product_id, ordered_date,
       expected_date, received_date, quantity, unit_cost_idr, po_status
FROM core.purchase_orders;

-- Marketing ----------------------------------------------------------------

CREATE VIEW analytics.dim_promotion AS
SELECT promotion_id, promo_code, promo_name, promo_type, discount_pct, channel_scope,
       start_date, end_date
FROM core.promotions;

CREATE VIEW analytics.fact_promotion_redemptions AS
SELECT redemption_id, promotion_id, order_id, discount_idr, redeemed_at
FROM core.promotion_redemptions;

CREATE VIEW analytics.fact_web_sessions AS
SELECT session_id, channel_id, customer_id, started_at, device_type, traffic_source,
       viewed_product, added_to_cart, reached_checkout, converted, order_id
FROM core.web_sessions;

-- Service ------------------------------------------------------------------

CREATE VIEW analytics.fact_support_tickets AS
SELECT ticket_id, ticket_number, customer_id, order_id, assigned_employee_id, created_at,
       contact_channel, ticket_category, subject, ticket_status, resolved_at, csat_score
FROM core.support_tickets;

-- People (no name, email, phone, or salary) --------------------------------

CREATE VIEW analytics.dim_employee AS
SELECT employee_id, employee_code, store_id, job_role, hire_date, termination_date,
       (termination_date IS NULL) AS is_active
FROM core.employees;

CREATE VIEW analytics.fact_sales_targets AS
SELECT store_id, month_start, target_net_revenue_idr
FROM core.sales_targets;

CREATE VIEW analytics.fact_store_daily_traffic AS
SELECT store_id, traffic_date, visitors
FROM core.store_daily_traffic;
