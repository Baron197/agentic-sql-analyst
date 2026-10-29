-- Applied after the bulk load: foreign keys (which validate every existing row,
-- so a broken seed fails the rebuild), check constraints, and indexes.

ALTER TABLE core.stores ADD FOREIGN KEY (region_id) REFERENCES core.regions;
ALTER TABLE core.categories ADD FOREIGN KEY (parent_category_id) REFERENCES core.categories;
ALTER TABLE core.suppliers ADD FOREIGN KEY (region_id) REFERENCES core.regions;
ALTER TABLE core.products ADD FOREIGN KEY (category_id) REFERENCES core.categories;
ALTER TABLE core.products ADD FOREIGN KEY (supplier_id) REFERENCES core.suppliers;
ALTER TABLE core.customers ADD FOREIGN KEY (region_id) REFERENCES core.regions;
ALTER TABLE core.employees ADD FOREIGN KEY (store_id) REFERENCES core.stores;

ALTER TABLE core.orders ADD FOREIGN KEY (customer_id) REFERENCES core.customers;
ALTER TABLE core.orders ADD FOREIGN KEY (store_id) REFERENCES core.stores;
ALTER TABLE core.orders ADD FOREIGN KEY (channel_id) REFERENCES core.channels;
ALTER TABLE core.orders ADD FOREIGN KEY (sales_employee_id) REFERENCES core.employees;
ALTER TABLE core.orders ADD CHECK (status IN ('completed', 'cancelled', 'refunded'));

ALTER TABLE core.order_items ADD FOREIGN KEY (order_id) REFERENCES core.orders;
ALTER TABLE core.order_items ADD FOREIGN KEY (product_id) REFERENCES core.products;
ALTER TABLE core.order_items ADD CHECK (quantity > 0 AND unit_price_idr > 0 AND discount_idr >= 0);
ALTER TABLE core.order_items ADD UNIQUE (order_id, line_number);

ALTER TABLE core.payments ADD FOREIGN KEY (order_id) REFERENCES core.orders;
ALTER TABLE core.returns ADD FOREIGN KEY (order_item_id) REFERENCES core.order_items;
ALTER TABLE core.returns ADD FOREIGN KEY (order_id) REFERENCES core.orders;
ALTER TABLE core.returns ADD CHECK (quantity > 0 AND refund_amount_idr >= 0);
ALTER TABLE core.shipments ADD FOREIGN KEY (order_id) REFERENCES core.orders;
ALTER TABLE core.shipments ADD FOREIGN KEY (destination_region_id) REFERENCES core.regions;

ALTER TABLE core.inventory_daily ADD FOREIGN KEY (store_id) REFERENCES core.stores;
ALTER TABLE core.inventory_daily ADD FOREIGN KEY (product_id) REFERENCES core.products;
ALTER TABLE core.purchase_orders ADD FOREIGN KEY (supplier_id) REFERENCES core.suppliers;
ALTER TABLE core.purchase_orders ADD FOREIGN KEY (store_id) REFERENCES core.stores;
ALTER TABLE core.purchase_orders ADD FOREIGN KEY (product_id) REFERENCES core.products;

ALTER TABLE core.promotion_redemptions ADD FOREIGN KEY (promotion_id) REFERENCES core.promotions;
ALTER TABLE core.promotion_redemptions ADD FOREIGN KEY (order_id) REFERENCES core.orders;
ALTER TABLE core.web_sessions ADD FOREIGN KEY (channel_id) REFERENCES core.channels;
ALTER TABLE core.web_sessions ADD FOREIGN KEY (customer_id) REFERENCES core.customers;
ALTER TABLE core.web_sessions ADD FOREIGN KEY (order_id) REFERENCES core.orders;

ALTER TABLE core.support_tickets ADD FOREIGN KEY (customer_id) REFERENCES core.customers;
ALTER TABLE core.support_tickets ADD FOREIGN KEY (order_id) REFERENCES core.orders;
ALTER TABLE core.support_tickets ADD FOREIGN KEY (assigned_employee_id) REFERENCES core.employees;

ALTER TABLE core.sales_targets ADD FOREIGN KEY (store_id) REFERENCES core.stores;
ALTER TABLE core.store_daily_traffic ADD FOREIGN KEY (store_id) REFERENCES core.stores;

CREATE INDEX ON core.orders (ordered_at);
CREATE INDEX ON core.orders (store_id);
CREATE INDEX ON core.orders (customer_id);
CREATE INDEX ON core.order_items (order_id);
CREATE INDEX ON core.order_items (product_id);
CREATE INDEX ON core.returns (order_id);
CREATE INDEX ON core.payments (order_id);
CREATE INDEX ON core.web_sessions (started_at);
CREATE INDEX ON core.inventory_daily (store_id, product_id);
