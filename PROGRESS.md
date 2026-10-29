# Progress

Updated by Claude at the end of every session. A fresh chat continues from here.

## Status

| Phase | Status | Notes |
|---|---|---|
| 0 Scaffold | **done** (2026-10-29) | all DoD items pass; see session log |
| 1 Synthetic enterprise database | **done** (2026-10-29) | all DoD items pass; see session log |
| 2 Safety layer | not started | next |
| 3 Eval harness, golden set, baseline | not started | |
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

- CI has never run on GitHub (nothing pushed). Its db tests assume the full-scale seed, which the workflow loads with `poe db-load` before `poe check`.
- Docker Desktop 4.80 on this machine crashed at startup because of leftover AF_UNIX socket files that Windows refuses to delete (error 1920). Workaround used on 2026-10-29: quit Docker Desktop and rename the folders aside: `%LOCALAPPDATA%\Docker\run` and `%LOCALAPPDATA%\docker-secrets-engine` (now `*.stale-20261029*`). They can be deleted after a reboot. If Docker fails to start again with "The file cannot be accessed by the system", repeat that. Quitting Docker Desktop normally (not killing it) should avoid it.

## Next step

Phase 2: Safety layer (BUILD_GUIDE §7 and §13), before any LLM code. Start with a plan covering:
- the `nlq_reader` role (SELECT on `analytics` only, `default_transaction_read_only = on`), created so it survives `db-reset` (D011);
- row-level security on region-scoped views keyed on `SET LOCAL app.region_ids`. Views read `core` as their owner, so RLS must be designed for views; check `security_invoker` views (PG15+) or security-barrier views filtering on `current_setting('app.region_ids')`. The region of an order is its store's region;
- masked views if any are needed (D010);
- the sqlglot validator using `data/dictionary.yaml` (allowed views/columns, `pii` flag, deny-listed functions);
- the EXPLAIN cost guard, the executor (read-only transaction, 5 s timeout, outer LIMIT 1000, pool);
- 60+ adversarial tests, including both defense-in-depth tests;
- `docs/SECURITY.md` with a threat → layer → test table.

## Session log

_(newest first: date, what was done, decisions, issues)_

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
