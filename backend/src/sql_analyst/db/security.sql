-- Safety layer in the database (Phase 2). Applied by db-load after views.sql.
-- Roles nlq_reader (LOGIN) and analytics_owner (NOLOGIN) are created by load.py
-- before this file runs, because they are cluster-level and need a password.
--
-- 1. Read-only role: nlq_reader may only SELECT the analytics views.
-- 2. Row-level security: region-scoped core tables have RLS policies that apply to
--    analytics_owner, the owner of every analytics view. Postgres checks a view's
--    base tables as the view's owner, so the policies apply to everyone who reads
--    the views, superusers included.
-- 3. Signed scope: the policies trust app.region_ids only if app.region_sig is a valid
--    HMAC of (region_ids | backend pid | transaction start) under a key that no
--    query role can read. Unset, malformed, or forged scope => zero rows.

CREATE SCHEMA rls;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA rls;

CREATE TABLE rls.signing_key (key bytea NOT NULL);  -- one row, inserted by load.py
REVOKE ALL ON rls.signing_key FROM PUBLIC;

-- The verified scope: the region_ids text ('all' or '1,2,3'), or NULL if not validly signed.
CREATE FUNCTION rls.verified_scope() RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, rls AS $$
DECLARE
    ids text := current_setting('app.region_ids', true);
    sig text := current_setting('app.region_sig', true);
    k bytea;
    msg text;
BEGIN
    IF ids IS NULL OR ids = '' OR sig IS NULL OR sig = '' THEN
        RETURN NULL;
    END IF;
    SELECT key INTO k FROM rls.signing_key;
    msg := ids || '|' || pg_backend_pid() || '|'
        || floor(extract(epoch FROM transaction_timestamp()) * 1000000)::bigint;
    IF k IS NULL OR encode(rls.hmac(convert_to(msg, 'UTF8'), k, 'sha256'), 'hex') IS DISTINCT FROM sig THEN
        RETURN NULL;
    END IF;
    RETURN ids;
END
$$;

CREATE FUNCTION rls.is_all_scope() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, rls AS $$
    SELECT coalesce(rls.verified_scope() = 'all', false)
$$;

CREATE FUNCTION rls.visible_regions() RETURNS SETOF smallint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, rls AS $$
    SELECT r.region_id
    FROM core.regions r, (SELECT rls.verified_scope() AS s) v
    WHERE CASE WHEN v.s = 'all' THEN true
               ELSE r.region_id = ANY (string_to_array(v.s, ',')::smallint[]) END
$$;

CREATE FUNCTION rls.visible_stores() RETURNS SETOF smallint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, rls AS $$
    SELECT s.store_id FROM core.stores s WHERE s.region_id IN (SELECT rls.visible_regions())
$$;

CREATE FUNCTION rls.visible_customers() RETURNS SETOF integer
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, rls AS $$
    SELECT c.customer_id FROM core.customers c WHERE c.region_id IN (SELECT rls.visible_regions())
$$;

CREATE FUNCTION rls.visible_orders() RETURNS SETOF integer
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, rls AS $$
    SELECT o.order_id FROM core.orders o WHERE o.store_id IN (SELECT rls.visible_stores())
$$;

-- Postgres checks EXECUTE on functions inside policies as the querying role, so the
-- reader needs EXECUTE. It gets no USAGE on schema rls, so its own SQL cannot call
-- these functions by name (policies reference them by OID, resolved at creation).
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA rls FROM PUBLIC;
GRANT USAGE ON SCHEMA rls TO analytics_owner;
GRANT EXECUTE ON FUNCTION rls.verified_scope(), rls.is_all_scope(), rls.visible_regions(),
    rls.visible_stores(), rls.visible_customers(), rls.visible_orders()
    TO analytics_owner, nlq_reader;

-- Row-level security on region-scoped core tables. Reference tables (calendar,
-- regions, channels, categories, products, suppliers, promotions) are not scoped.
-- Each policy short-circuits for the 'all' scope; otherwise rows follow their store,
-- order, or customer. Rows with no region (head-office staff, anonymous sessions)
-- are visible only to the 'all' scope.
DO $$
DECLARE
    p record;
BEGIN
    FOR p IN
        SELECT * FROM (VALUES
            ('stores',                'region_id IN (SELECT rls.visible_regions())'),
            ('customers',             'region_id IN (SELECT rls.visible_regions())'),
            ('orders',                'store_id IN (SELECT rls.visible_stores())'),
            ('order_items',           'order_id IN (SELECT rls.visible_orders())'),
            ('payments',              'order_id IN (SELECT rls.visible_orders())'),
            ('returns',               'order_id IN (SELECT rls.visible_orders())'),
            ('shipments',             'order_id IN (SELECT rls.visible_orders())'),
            ('promotion_redemptions', 'order_id IN (SELECT rls.visible_orders())'),
            ('employees',             'store_id IN (SELECT rls.visible_stores())'),
            ('inventory_daily',       'store_id IN (SELECT rls.visible_stores())'),
            ('purchase_orders',       'store_id IN (SELECT rls.visible_stores())'),
            ('sales_targets',         'store_id IN (SELECT rls.visible_stores())'),
            ('store_daily_traffic',   'store_id IN (SELECT rls.visible_stores())'),
            ('support_tickets',       'customer_id IN (SELECT rls.visible_customers())'),
            ('web_sessions',          'order_id IN (SELECT rls.visible_orders()) OR '
                                      '(order_id IS NULL AND customer_id IN (SELECT rls.visible_customers()))')
        ) AS t(tbl, rule)
    LOOP
        EXECUTE format('ALTER TABLE core.%I ENABLE ROW LEVEL SECURITY', p.tbl);
        EXECUTE format(
            'CREATE POLICY region_scope ON core.%I FOR SELECT TO analytics_owner '
            'USING ((SELECT rls.is_all_scope()) OR %s)', p.tbl, p.rule);
    END LOOP;
END
$$;

-- The views' owner reads core (subject to the policies above); it cannot log in.
GRANT USAGE ON SCHEMA core TO analytics_owner;
GRANT SELECT ON ALL TABLES IN SCHEMA core TO analytics_owner;
DO $$
DECLARE
    v record;
BEGIN
    FOR v IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'analytics' AND c.relkind = 'v'
    LOOP
        EXECUTE format('ALTER VIEW analytics.%I OWNER TO analytics_owner', v.relname);
    END LOOP;
END
$$;

-- The agent's role: SELECT on analytics views only. No access to core or rls.
REVOKE ALL ON SCHEMA core FROM PUBLIC;
REVOKE ALL ON SCHEMA rls FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA analytics TO nlq_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO nlq_reader;
