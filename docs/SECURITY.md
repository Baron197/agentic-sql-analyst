# Security

The model is treated as untrusted input. Every SQL statement it writes passes through independent layers, and the two most important guarantees are enforced by Postgres itself, not by the prompt or by Python:

1. **Read-only by construction.** The SQL validator, a `READ ONLY` transaction, and the privileges of the `nlq_reader` role each block writes on their own. Tests disable the other two layers and show each one holding.
2. **You only see what you're allowed to see.** Row-level security in Postgres scopes every region-bound view to the signed-in user's regions. The scope is HMAC-signed, so SQL that bypasses the validator still cannot widen it.

All data is synthetic (see [DATA.md](DATA.md)); this is a portfolio project built to production standards.

## Layers

| # | Layer | Where | Phase |
|---|---|---|---|
| 1 | Input guard (length, write intents, personal-data requests, off-topic) | agent `guard_input` | 4 |
| 2 | SQL validator (sqlglot AST) | `backend/src/sql_analyst/safety/validator.py` | 2 |
| 3 | Row cap: outer `LIMIT 1001`, return 1,000 and flag truncation | `safety/executor.py` | 2 |
| 4 | Cost guard: `EXPLAIN (FORMAT JSON)`, reject plans above 250,000 | `safety/cost_guard.py` | 2 |
| 5 | Executor: `nlq_reader` role, `READ ONLY` transaction, 5 s `statement_timeout`, connection pool | `safety/executor.py`, `db/load.py` | 2 |
| 6 | Row-level security with a signed region scope | `db/security.sql`, `safety/scope.py` | 2 |
| 7 | Hostile data: rows go to the model as delimited data; answers are templates | agent | 4 |
| 8 | Budget guard, rate limit, daily spend cap, kill switch | agent, API | 4-5 |

### Layer 2: the SQL validator

1. At most 10,000 characters; no control or invisible format characters anywhere; outside string literals, ASCII only (stops lookalike letters such as a Cyrillic `е` in `SЕLECT`).
2. Exactly one statement, and it is a query: `SELECT`, `WITH … SELECT`, or a set operation.
3. No write, DDL, utility, or locking node anywhere in the tree. This catches data-modifying CTEs (`WITH d AS (DELETE …)`), `SELECT … INTO`, `FOR UPDATE`, `COPY`, `SET`, `CALL`, `EXPLAIN`, and transaction control.
4. Functions: functions sqlglot does not model (Postgres-specific ones) must be on an **allow-list**; every function name is also checked against a **deny-list** (`pg_*`, `lo_*`, `dblink`, `set_config`, `current_setting`, `query_to_xml`, `version`, `current_user`, …). Schema-qualified function calls and casts to `reg*` types are rejected.
5. Tables: only the views in `data/dictionary.yaml`, in schema `analytics` (or names of CTEs in the same query). No system catalogs, `information_schema`, `core`, or `rls`.
6. Columns: every column must exist in the dictionary (sqlglot qualifies and expands `*`); columns flagged `pii: true` are rejected wherever they are read, including through subqueries and CTEs.

The executor runs the SQL **regenerated from the parsed tree, with comments removed**, never the original text. Postgres therefore only sees what the validator parsed, which rules out parser-differential tricks (for example comments that one parser nests and the other does not).

### Layers 3-5: the executor and the database role

- `nlq_reader`: `LOGIN`, not superuser, no `CREATEDB`, `CREATEROLE`, `REPLICATION`, or `BYPASSRLS`; `USAGE` on schema `analytics` and `SELECT` on its views only; no access to `core` or `rls`; `TEMPORARY` revoked on the database; role defaults `default_transaction_read_only = on`, `statement_timeout = 5s`, `search_path = analytics`; connection limit 20.
- Every query runs in a transaction opened with `BEGIN READ ONLY` (psycopg `read_only = True`), with `SET LOCAL statement_timeout` and the signed region scope.
- The views are owned by `analytics_owner` (`NOLOGIN`, no `BYPASSRLS`), so the views read `core` as a role that row-level security applies to.

### Layer 6: row-level security with a signed scope

Postgres row-level security applies to tables, not views. A view reads its base tables with its owner's privileges, so the policies are written on the `core` tables for `analytics_owner`, the owner of every view. Everyone who reads the views is therefore scoped, the admin role included.

For each request the executor:
1. reads `pg_backend_pid()` and the transaction start time;
2. sets `app.region_ids` (`all` or a list such as `1,2,3,4,5`) and `app.region_sig = HMAC-SHA256(key, region_ids | pid | transaction start)` with `set_config(…, true)` (transaction-local).

The policies call `rls.verified_scope()`, a `SECURITY DEFINER` function that recomputes the HMAC with a key stored in `rls.signing_key`, which no query role can read. An unset, malformed, forged, or replayed scope (another transaction, another connection, or region IDs changed after signing) yields **zero rows**: the design fails closed.

Rows follow their region:
- stores and customers by `region_id`;
- orders by their store;
- order lines, payments, returns, shipments, and promotion redemptions by their order;
- inventory, purchase orders, targets, footfall, and employees by their store;
- support tickets by the customer;
- web sessions by their order, or by the customer for sessions with no order.

Reference data (calendar, regions, channels, categories, products, suppliers, promotions) is not scoped. Rows with no region, such as head-office staff and anonymous web sessions, are visible only to the `all` scope.

`nlq_reader` has `EXECUTE` on the `rls` functions (Postgres checks function privileges in policies as the querying role) but no `USAGE` on schema `rls`, so its own SQL cannot call them by name. The policies resolved them by OID when they were created.

Demo scopes (users are seeded in Phase 5): `analyst@demo` = `all`; `manager.jakarta@demo` = the Jabodetabek region group (region IDs 1-5: Jakarta, Bogor, Depok, Tangerang, Bekasi).

## Threat model

Every threat maps to at least one test. Paths are relative to `backend/tests/`; a test (`unit/test_security_doc.py`) fails if any referenced test does not exist.

| Threat | Layer(s) | Tests |
|---|---|---|
| The model writes data (DELETE, UPDATE, INSERT, TRUNCATE) | 2, 5 (transaction), 5 (role) | `safety/test_validator.py::test_adversarial_sql_is_rejected`, `safety/test_defense_in_depth.py::test_delete_sent_straight_to_the_database_is_refused`, `safety/test_defense_in_depth.py::test_layer_validator_alone_rejects_writes`, `safety/test_defense_in_depth.py::test_layer_read_only_transaction_alone_blocks_even_the_superuser`, `safety/test_defense_in_depth.py::test_layer_role_privileges_alone_block_writes_in_a_read_write_transaction` |
| Schema changes (DROP, CREATE, ALTER, GRANT, CREATE EXTENSION) | 2, 5 | `safety/test_validator.py::test_adversarial_sql_is_rejected`, `safety/test_defense_in_depth.py::test_delete_sent_straight_to_the_database_is_refused` |
| A write hidden inside a query (data-modifying CTE, SELECT INTO, FOR UPDATE) | 2, 5 | `safety/test_validator.py::test_adversarial_sql_is_rejected` |
| Stacked statements and comment tricks | 2 (one statement; regenerated SQL) | `safety/test_validator.py::test_adversarial_sql_is_rejected`, `safety/test_validator.py::test_executed_sql_is_regenerated_without_comments` |
| Unicode lookalikes, invisible characters, null bytes | 2 | `safety/test_validator.py::test_adversarial_sql_is_rejected` |
| Session tampering (SET, RESET, SET ROLE, set_config, transaction control) | 2, 5, 6 | `safety/test_validator.py::test_adversarial_sql_is_rejected`, `safety/test_defense_in_depth.py::test_reader_role_cannot_reach_core_secrets_files_or_other_roles`, `safety/test_rls.py::test_forged_scope_without_valid_signature_sees_zero_rows` |
| A manager reads another region's rows (filters, subqueries, CTEs, UNION, child tables) | 6 | `safety/test_rls.py::test_manager_cross_region_attempts_return_zero_rows`, `safety/test_rls.py::test_manager_rows_stay_in_scope_in_every_scoped_view`, `safety/test_rls.py::test_manager_order_child_rows_belong_to_visible_orders`, `safety/test_defense_in_depth.py::test_manager_hand_written_sql_against_another_region_returns_zero_rows` |
| Forged, widened, or replayed region scope; missing scope | 6 | `safety/test_rls.py::test_forged_scope_without_valid_signature_sees_zero_rows`, `safety/test_rls.py::test_valid_manager_signature_cannot_be_reused_for_other_regions`, `safety/test_rls.py::test_signature_is_bound_to_its_transaction`, `safety/test_rls.py::test_no_scope_means_zero_rows`, `safety/test_rls.py::test_superuser_reading_the_views_without_scope_sees_zero_rows` |
| Personal data exposure (names, emails, phones, salaries) | schema design, 2, 5 | `db/test_database.py::test_no_personal_data_in_analytics`, `safety/test_validator.py::test_columns_flagged_as_personal_data_are_rejected_even_if_documented`, `safety/test_validator.py::test_adversarial_sql_is_rejected` |
| Reading system catalogs, `core`, `rls`, or the signing key | 2, 5 | `safety/test_validator.py::test_adversarial_sql_is_rejected`, `safety/test_defense_in_depth.py::test_reader_role_cannot_reach_core_secrets_files_or_other_roles` |
| File, network, large-object, or server functions (pg_read_file, lo_import, dblink, COPY TO) | 2, 5 | `safety/test_validator.py::test_adversarial_sql_is_rejected`, `safety/test_defense_in_depth.py::test_reader_role_cannot_reach_core_secrets_files_or_other_roles` |
| Privilege escalation of the agent role (SET ROLE, ALTER ROLE, GRANT, temp tables) | 5 | `safety/test_defense_in_depth.py::test_reader_role_attributes`, `safety/test_defense_in_depth.py::test_layer_role_privileges_alone_block_writes_in_a_read_write_transaction`, `safety/test_defense_in_depth.py::test_reader_role_cannot_reach_core_secrets_files_or_other_roles` |
| Resource exhaustion through cross joins or huge generated series | 4 | `safety/test_executor.py::test_cost_guard_rejects_cross_joins`, `safety/test_executor.py::test_huge_generate_series_is_stopped_by_the_cost_guard` |
| Long-running queries (pg_sleep, recursive CTEs the planner underestimates) | 2, 5 (timeout) | `safety/test_validator.py::test_adversarial_sql_is_rejected`, `safety/test_executor.py::test_statement_timeout_cancels_slow_queries` |
| Huge result sets sent to the model or the browser | 3 | `safety/test_executor.py::test_row_cap_truncates_and_reports_it` |
| The safety layer blocks legitimate analysis (false positives) | 2, 4 | `safety/test_validator.py::test_ordinary_analytical_sql_is_allowed`, `safety/test_executor.py::test_allowed_sql_runs_for_both_roles` |

### Threats covered in later phases

| Threat | Layer | Phase |
|---|---|---|
| Prompt injection through data (the planted support ticket `TCK-2026-004660`) | 7 | 4 (eval case in Phase 3) |
| Write intents, personal-data requests, off-topic questions in the question itself | 1 | 4 |
| Runaway cost or loops (LLM calls, tokens, wall time, repairs) | 8 | 4 |
| Abuse of the public API (rate limit, daily spend cap, kill switch, auth) | 8 | 5 |

## Cost-limit calibration (2026-10-29)

Planner costs of the wrapped query (`SELECT * FROM (…) LIMIT 1001`) on the full seed, the same for the analyst and the Jakarta manager:

| Query | Planner cost |
|---|---:|
| Glossary metrics (6) | 1,918 - 12,461 |
| Monthly revenue by category (4-way join) | 13,892 |
| Inventory × product × store × category aggregate | 26,668 |
| Correlated subquery per customer | 29,598 |
| **Limit** | **250,000** |
| Inventory × stores cross join | 317,301 |
| Dates × orders cross join | 802,740 |
| Order items × returns on a non-key condition | 8,007,056 |
| Sessions × customers cross join | 44,565,696 |
| Orders × order items cross join | 73,147,054 |

The limit leaves about 8× headroom over the heaviest legitimate query measured. A small dimension × fact cross join (stores × orders, cost 21,610) passes, but it is cheap to run; anything slow that the planner underestimates is stopped by the 5 s timeout. The limit is a setting (`QUERY_COST_LIMIT`) and will be revisited with the Phase 3 eval queries.

## Residual risks and limits

- **The validator depends on sqlglot.** A query sqlglot parses differently from Postgres could slip past rules 2-6, but the executor runs sqlglot's regenerated SQL, and layers 5-6 do not depend on the validator at all.
- **The allow-list may reject a legitimate function.** That shows up as a refusal, never as a leak. Functions are added when the eval shows a real need.
- **The admin role can read the signing key.** The admin role (`POSTGRES_USER`) owns everything and is used only by `db-load` and tests, never by the agent or the API. In a deployment the key and the admin password live in the platform's secret store (Phase 8).
- **`now()` and `current_date`** are allowed and return the real date, while the data ends on 30 Sep 2026. Handling "this month" is the agent's job (Phase 4).
- **Statement timeout vs. long-planned queries:** EXPLAIN plans but does not run; a query whose cost the planner underestimates (recursive CTEs) is caught only by the 5 s timeout.
