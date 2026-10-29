# Progress

Updated by Claude at the end of every session. A fresh chat continues from here.

## Status

| Phase | Status | Notes |
|---|---|---|
| 0 Scaffold | **done** (2026-10-29) | all DoD items pass; see session log |
| 1 Synthetic enterprise database | **done** (2026-10-29) | all DoD items pass; see session log |
| 2 Safety layer | **done** (2026-10-29) | all DoD items pass; see session log |
| 3 Eval harness, golden set, baseline | not started | next |
| 4 Agent core | not started | |
| 5 API | not started | |
| 6 Web app | not started | |
| 7 Real-mode evaluation | not started | needs Baron's budget OK |
| 8 Deploy | not started | |
| 9 Portfolio packaging | not started | |

## Decided in the planning chat (2026-10-29)

- Project: an agentic NLQ / text-to-SQL analyst over a fictional Indonesian retailer (PT Arunika Niaga), English and Bahasa Indonesia.
- Stack: Python 3.12 + uv, LangGraph, FastAPI, PostgreSQL 16 + pgvector, sqlglot, fastembed, React + TypeScript + Vite.
- Four guarantees: read-only by construction, row-level security in Postgres, the model never types a number, shows its work.
- Build order: safety and evaluation before the agent.
- Provider-agnostic LLM interface; fake adapter for keyless tests and CI.

## Open questions for Baron

- Live LLM provider and model for Phase 4 (options and rough costs in BUILD_GUIDE §8.4).
- Deploy target for Phase 8: Azure (A) or the existing AWS EC2 (B).
- GitHub repository name and visibility (only when Baron says to push). CI has not run on GitHub yet; it is only schema-validated locally.
- License: none chosen yet (the flagship uses MIT). Add before the repo goes public.

## Open issues

- CI has never run on GitHub (nothing pushed). Its db tests assume the full-scale seed, which the workflow loads with `poe db-load` before `poe check`; the workflow sets throwaway `NLQ_READER_PASSWORD` and `RLS_SIGNING_KEY` values.
- Layers 1 (input guard), 7 (hostile data), and 8 (budget, rate limit, spend cap, kill switch) of BUILD_GUIDE §7 are not built yet; they belong to Phases 4-5 and are listed in docs/SECURITY.md under "Threats covered in later phases".
- The function allow-list (D014) may refuse a legitimate function the agent needs; watch for `forbidden_function` errors in the Phase 3/4 eval and add functions deliberately.
- Docker Desktop 4.80 on this machine crashed at startup because of leftover AF_UNIX socket files that Windows refuses to delete (error 1920). Workaround used on 2026-10-29: quit Docker Desktop and rename the folders aside: `%LOCALAPPDATA%\Docker\run` and `%LOCALAPPDATA%\docker-secrets-engine` (now `*.stale-20261029*`). They can be deleted after a reboot. If Docker fails to start again with "The file cannot be accessed by the system", repeat that. Quitting Docker Desktop normally (not killing it) should avoid it.

## Next step

Phase 3: Evaluation harness, golden set, and baseline (BUILD_GUIDE §9 and §13). Start with a plan covering:
- about 100 YAML cases in `eval/cases/dev.yaml` (~40) and `eval/cases/test.yaml` (~60), ~20% Indonesian, across every category in §9 (including `access_control` cases for the Jakarta manager, adversarial cases, and one for the planted injection ticket `TCK-2026-004660`). Gold SQL must pass the validator and run through `safety.executor.Executor` with the case's user scope;
- the harness `uv run poe eval --mode keyless|live --split dev|test --repeats N --system agent|baseline --model …`, metrics (EX strict/lenient, valid SQL rate, safety block rate, refusal accuracy, latency/cost), and JSON + markdown output in `eval/results/`;
- the single-prompt baseline, `data/examples.yaml`, and the leakage-guard test;
- the 10-question live baseline run needs Baron's OK and a cost estimate first. Phase 3 needs an LLM provider for that run (open question above).

## Session log

_(newest first: date, what was done, decisions, issues)_

### 2026-10-29: Phase 2 safety layer (done)

**Built**
- `db/security.sql`, applied by `db-load` after the views:
  - schema `rls` with pgcrypto, `rls.signing_key`, `SECURITY DEFINER` functions `verified_scope()`, `is_all_scope()`, `visible_regions/stores/customers/orders()`;
  - row-level security policies on 15 region-scoped `core` tables for `analytics_owner`;
  - all analytics views owned by `analytics_owner`;
  - grants: `nlq_reader` gets SELECT on analytics only, `EXECUTE` on the rls functions without schema `USAGE`, and no access to `core`.
- `db/load.py` `ensure_roles()`:
  - creates or updates `nlq_reader` (LOGIN; read-only transactions by default, 5 s timeout, `search_path = analytics`, connection limit 20, TEMPORARY revoked) and `analytics_owner` (NOLOGIN);
  - loads the signing key.
- `safety/`:
  - `scope.py`: `UserScope`, `apply_scope` (HMAC-signed, bound to the backend pid and transaction start);
  - `validator.py`: sqlglot rules 1-6;
  - `cost_guard.py`: EXPLAIN limit 250,000;
  - `executor.py`: psycopg pool, READ ONLY transaction, timeout, signed scope, cost check, outer LIMIT 1001 with truncation flag, typed errors;
  - `errors.py`.
- Settings: `NLQ_READER_PASSWORD`, `RLS_SIGNING_KEY` (generated into the local `.env`, names in `.env.example`, throwaway values in CI), `query_timeout_ms`, `query_row_limit`, `query_cost_limit`.
- Tests (282 total; the safety suite is 247):
  - `safety/test_validator.py`: 101 adversarial cases, 21 must-pass queries, PII-flag and regeneration tests;
  - `safety/test_executor.py`: the must-pass queries for both scopes, row cap, cost guard on 5 cross joins and a huge `generate_series`, timeout, error mapping;
  - `safety/test_rls.py`: per-view scoping, 10 cross-region attempts, forgery, widening, replay, no scope, admin without scope;
  - `safety/test_defense_in_depth.py`: the two guide tests, each write layer alone, and reader-role probes;
  - `unit/test_security_doc.py`: every threat in SECURITY.md maps to existing tests.
- The Phase 1 db test fixture now applies a signed `all` scope. Without it, the orphan test passed vacuously on zero rows.
- `docs/SECURITY.md`: layers, RLS design, threat → layer → test table, cost calibration, residual risks.
- Test folders are now packages (`__init__.py`) so the safety tests can share fixtures.
- Added sqlglot 30.25.0 and psycopg-pool 3.3.3.

**DoD evidence (2026-10-29, from a wiped volume)**
- `db-wipe` then `db-reset`: roles, policies, and grants are created on a fresh cluster in 11.2 s.
- All safety tests pass, including both defense-in-depth tests:
  - `test_delete_sent_straight_to_the_database_is_refused`: 8 write statements, all refused;
  - `test_manager_hand_written_sql_against_another_region_returns_zero_rows`: zero rows through the full path, with the validator bypassed, and with tampering.
- The threat table maps every threat to a test: `unit/test_security_doc.py` passes, and it was shown to fail when a referenced test is missing.
- `uv run poe check`: ruff clean, 52 files formatted, workflow schema valid, 282 passed.
- The seed is unchanged: combined sha256 `917e52ad…f351f938`, as in Phase 1.

**Findings along the way**
- Postgres checks `EXECUTE` on functions used in policies as the querying role, not the view owner, so `nlq_reader` needs EXECUTE. It gets no schema USAGE, which keeps the functions unreachable from its own SQL.
- Postgres 16 estimates `generate_series` rows exactly, so the cost guard catches huge series. Recursive CTEs are underestimated, and only the timeout stops those (both tested).
- `ruff check --fix` / `ruff format` left literal homoglyphs and invisible characters in place of `\u` escapes in the adversarial test strings. They are restored as escapes, so no invisible characters sit in the source.

**Decisions:** D012-D016 in `docs/DECISIONS.md`:
- row-level security on `core` for the views' owner;
- the HMAC-signed scope;
- function allow-list plus deny-list;
- the executor runs regenerated SQL;
- Jakarta manager = Jabodetabek, cost limit 250,000.

### 2026-10-29: Phase 1 synthetic enterprise database (done)

**Built**
- `backend/src/sql_analyst/db/`:
  - `schema.sql`: 22 `core` tables;
  - `constraints.sql`: 33 foreign keys, checks and indexes, added after the bulk load;
  - `views.sql`: 22 `analytics` views with no personal data;
  - `calendar.py`: fiscal year starting 1 April, government Ramadan/Idulfitri dates, Harbolnas;
  - `seed/`: deterministic generator split into `reference.py`, `catalog.py`, `sales.py`, `ops.py`, `common.py`;
  - `load.py` (COPY with timed stages) and `checksum.py`.
- `data/dictionary.yaml`: 22 views and 161 columns, each with a description, type, EN/ID synonyms, categorical flag and examples; plus business rules, 35 join paths, and 6 glossary metrics with canonical SQL. Pydantic models and loader are in `dictionary/`; `dictionary/values.py` is the value-index source (36 categorical columns).
- Poe tasks: `db-load`, `db-reset` (= `db-up` + `db-load`), `db-checksum`, `db-wipe`. CI now runs `db-load` before `check`.
- Tests (35 total):
  - unit: calendar, seed determinism across processes and hash seeds, order totals equal their lines, dictionary structure;
  - db: row-count ranges, every declared FK validated, no orphans on any join path, dictionary equals the analytics columns and types exactly, glossary SQL runs and gives plausible values, no personal data in analytics, the injection row, the traps, value-index coverage.
- `docs/DATA.md`: coverage, row counts, mermaid ER diagram, patterns, the traps table, and Ramadan/Idulfitri dates with sources.
- Added faker 40.44.0 and pyyaml.

**DoD evidence (2026-10-29)**
- `db-reset` rebuilds in under 2 minutes: 17.6 s wall clock from a wiped volume (container creation included); `db-load` alone takes 8.5-8.9 s.
- Row counts in expected ranges: `test_row_counts_in_expected_ranges` passes. 60,046 orders, 144,369 order lines, 20,000 customers, 40 stores, 12 cities, 1,496,685 rows in total.
- FK integrity: all 33 declared foreign keys are created and validated, and there are 0 orphans along all 35 join paths.
- Identical checksums on two rebuilds, and on a third from a wiped volume: combined sha256 `917e52ad9b2f5724c19375a8e486b0786bedabfbf3bc350986a3a6102351f938` each time.
- 100% of analytics columns described: the dictionary matches the database exactly (161 columns, names and types), each description is at least 10 characters.
- Every glossary SQL runs: gross sales Rp 206,481,408,300; net revenue Rp 192,701,374,149; AOV Rp 3,480,887; return rate 0.0430; active customers 3,021; conversion rate 0.0834.
- `uv run poe check`: ruff clean, 36 files formatted, workflow schema valid, 35 passed.

**Decisions:** D006-D011 in `docs/DECISIONS.md`:
- `127.0.0.1` instead of `localhost`: the IPv6 fallback added 130 s to every connection, which first made `db-load` take 271 s;
- 183-day inventory window;
- pure-Python seed with per-domain string-seeded RNGs;
- metric edge cases (refunds attributed to the order's date; active customers as of the last order date);
- personal data omitted from analytics rather than masked;
- `db-reset` keeps the volume, `db-wipe` deletes it.
Also: ruff ignores E501, because line length is the formatter's job.

### 2026-10-29: Phase 0 scaffold (done)

**Built**
- `git init` (branch `main`, repo-local author `Baron Purwa Hartono <Baron197@users.noreply.github.com>`), `.gitignore`, `.gitattributes` (LF), `.python-version` (3.12).
- `pyproject.toml`: package `sql_analyst` in `backend/src` (uv_build), deps pydantic-settings + psycopg 3; dev group ruff, pytest, poethepoet, check-jsonschema; poe tasks `check`, `test`, `lint`, `format`, `lint-ci`, `db-up`, `db-down`, `db-reset`, `db-ping`, `ask`, `eval` (the last two are stubs that exit 2).
- `docker-compose.yml`: `pgvector/pgvector:pg16`, healthcheck, bound to 127.0.0.1, password required from `.env`. `.env.example` (secret names only); local `.env` generated with a random password.
- `backend/src/sql_analyst/`: `config.py` (Settings), `db/ping.py`, `cli.py`, empty subpackages from §5 with docstrings.
- Tests: `backend/tests/unit/test_config.py` (2 tests), `backend/tests/db/test_ping.py` (marked `db`), `conftest.py` skip/require logic.
- `.github/workflows/ci.yml`: backend job with a pgvector service, `uv sync --locked`, `poe check`, `poe db-ping`; keyless, `permissions: contents: read`. Web/Docker jobs are placeholders.
- `docs/DECISIONS.md` (D001–D005), README stub (WIP + fictional-data notice), CLAUDE.md Environment section now lists the real commands.

**DoD evidence (2026-10-29)**
- `uv run poe check`: ruff "All checks passed!", "19 files already formatted", workflow schema "ok -- validation done", pytest "3 passed" (db test ran against the live container, not skipped).
- `uv run poe db-up`: "Container agentic-sql-analyst-db-1 Healthy"; `docker compose ps`: "Up (healthy) 127.0.0.1:5432->5432/tcp".
- `uv run poe db-ping`: "db-ping OK: localhost:5432/arunika, PostgreSQL 16.14 (Debian 16.14-1.pgdg12+1)", "pgvector extension: available".
- CI YAML valid against the GitHub-workflow schema; a negative test (a misspelled `runs-on` key) was rejected, which shows the check works.
- `uv run poe db-reset`: volume removed, container healthy again.
- First commit made.

**Decisions:** D001–D005 in `docs/DECISIONS.md` (uv_build with `backend/src`, Python pinned to 3.12, check-jsonschema for the workflow, db tests skip locally but are required in CI, the db bound to localhost with no default password).
