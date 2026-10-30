# Progress

Updated by Claude at the end of every session. A fresh chat continues from here.

## Status

| Phase | Status | Notes |
|---|---|---|
| 0 Scaffold | **done** (2026-10-29) | all DoD items pass; see session log |
| 1 Synthetic enterprise database | **done** (2026-10-29) | all DoD items pass; see session log |
| 2 Safety layer | **done** (2026-10-29) | all DoD items pass; see session log |
| 3 Eval harness, golden set, baseline | **done** (2026-10-30) | all DoD items pass; see session log |
| 4 Agent core | **in progress** | all DoD items pass except the live agent-vs-baseline run on dev (needs Baron's OK) |
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

- Live LLM provider: Baron has an OpenAI key; the Phase 3 cost-tracking run used `gpt-6-luna` (D023). Both the OpenAI and Anthropic adapters exist. The final model choice is Phase 7.
- Deploy target for Phase 8: Azure (A) or the existing AWS EC2 (B).
- GitHub repository name and visibility (only when Baron says to push). CI has not run on GitHub yet; it is only schema-validated locally.
- License: none chosen yet (the flagship uses MIT). Add before the repo goes public.

## Open issues

- CI has never run on GitHub (nothing pushed). Its db tests assume the full-scale seed, which the workflow loads with `poe db-load` before `poe check`; the workflow sets throwaway `NLQ_READER_PASSWORD` and `RLS_SIGNING_KEY` values.
- Layer 8's API half (rate limit, daily spend cap, kill switch) belongs to Phase 5. Layers 1, 7, and the agent budget guard are built (Phase 4).
- The function allow-list (D014) may refuse a legitimate function the agent needs; watch for `forbidden_function` errors in the Phase 3/4 eval and add functions deliberately.
- Gold SQL is Claude's reading of each question. Baron should spot-check the ambiguous and metric-definition cases before any test-split number is quoted.
- Whether a live model's answer repeats the planted injection (t056) is not scored automatically (D020). Templates make typed figures impossible, but template prose is still model text; check t056 in the Phase 7 live test-split run.
- The embedding model downloads from Hugging Face on the first `index-build` (unauthenticated; ~220 MB). On Windows, huggingface_hub warns that symlinks are unsupported; the poe tasks silence the warning and caching still works.
- **Recurring (2026-10-29 and 2026-10-30):** Docker Desktop 4.80 on this machine crashed at startup because of leftover AF_UNIX socket files that Windows refuses to delete (error 1920). Workaround used on 2026-10-29: quit Docker Desktop and rename the folders aside: `%LOCALAPPDATA%\Docker\run` and `%LOCALAPPDATA%\docker-secrets-engine` (now `*.stale-20261029*`). They can be deleted after a reboot. If Docker fails to start again with "The file cannot be accessed by the system", repeat that. Quitting Docker Desktop normally (not killing it) should avoid it, but it happened again on 2026-10-30 after a normal session end (folders renamed to `*.stale-20261030`). The crash is in Docker's "Inference manager" (Docker Model Runner); turning that feature off in Docker Desktop settings may stop it. That is Baron's call, since it changes his Docker configuration.

## Next step

Finish Phase 4 with the last DoD item: **the live agent-vs-baseline run on `dev`, with Baron's OK**.
- Commands (each prints its estimate first; nothing is spent without `--confirm-live`):
  - `uv run poe eval --system agent --mode live --split dev --model gpt-6-luna --confirm-live`
  - `uv run poe eval --system baseline --mode live --split dev --model gpt-6-luna --confirm-live`
- Estimated upper bound, 40 questions × 1 repeat, no caching assumed: agent ≤ $0.19, baseline ≤ $0.09 (total ≤ $0.28). Phase 3's measured cost was ~7× below its estimate.
- Then commit the results, write the comparison in this file (date, model, n, repeats; dev is for tuning, so these are not reportable accuracy numbers), mark Phase 4 done, and stop. Phase 5 (API) starts only when Baron says so.

## Session log

_(newest first: date, what was done, decisions, issues)_

### 2026-10-30: Phase 4 agent core (built and tested keylessly; live run pending)

**Built**
- `agent/`: LangGraph graph (`graph.py`) with nodes guard_input → retrieve_context → generate_sql → validate_sql → execute → check_result → write_answer → render_numbers → finalize, plus refuse and budget_stop. Nodes leave the default path through `goto`; every edge goes through the budget guard (`budget.py`).
  - `guard.py`: deterministic input rules (EN/ID) and language detection; optional LLM classifier, off by default.
  - `nodes/sql.py`: structured SQL draft, validation, execution (validated again before running), repairs ≤ 3.
  - `nodes/check.py`: empty / all-NULL / implausible / negative-count / truncated checks, one retry; optional critic, off by default.
  - `nodes/answer.py` + `render.py`: templates with slots, locale formatting (`IDR 1.23B`, `Rp 1,23 miliar`, percentages), digit rejection, one retry then a table-only answer; chart choice by result shape.
  - `nodes/finalize.py`: `AgentResult` (answer, SQL, rows, assumptions, caveats, chart, trace, per-call usage, totals) saved to `runs/<date>.jsonl`.
  - `prompts/*.md`, `texts.py` (code-written sentences EN/ID), `keyless.py` + `data/demo.yaml` (8 demo questions), `factory.py`.
- `retrieval/`: corpus (217 chunks), multilingual fastembed embeddings stored in pgvector (`poe index-build`, schema `retrieval`), BM25 + vector fused by RRF, rapidfuzz value matching (652 values), join bridging.
- `observability.py` (trace and usage totals, JSONL run store); `users.py` (demo scopes, shared with the eval).
- CLI: `uv run poe ask "…" [--user] [--mode live --model M] [--json]`; with no question it lists the demo questions.
- Eval: `--system agent` with `--ablation` and `--critic`, a `repair_rate` metric, and grounding scored on the text the model typed (`Prediction.model_text`). The cost estimate covers the agent (4 calls per question).
- Moved shared code into the package: `dictionary/render.py` (the baseline prompt is byte-identical, verified), `retrieval/examples.py`, `agent/grounding.py` (re-exported by `eval/metrics.py`).
- Safety additions: the validator rejects `retrieval.*` (2 new adversarial cases, 103 total); `nlq_reader` cannot write the index; the threat table now covers layers 1, 7, 8 with tests.
- CI: caches the embedding model, runs `index-build`, and adds a keyless agent eval.

**Decisions:** D024 (multilingual embeddings), D025 (pgvector `retrieval` schema), D026 (value matching, join bridging), D027 (grounding on model-typed text), D028 (ablations; critic and LLM guard off), D029 (budget, repair, fallback semantics), D030 (keyless demo mode, run store).

**DoD evidence (all keyless, no API key)**
- `REQUIRE_DB=1 uv run poe check`: 680 passed (451 before), lint, format, and workflow schema clean.
  - unit tests per node: `backend/tests/agent/test_nodes.py`, `test_render.py`, `test_guard.py`, `test_retrieval.py`;
  - graph tests with the fake LLM for success, repair, unsafe refusal, unanswerable refusal, budget stop, and grounding rejection (plus capped repairs, empty-result retry, critic, model failures, ablations, prompt-cache stability): `test_graph.py`, 24 tests;
  - keyless end to end for every demo question and both users against the real database, index, and RLS: `test_keyless_e2e.py`. The manager sees 20 Jabodetabek stores, the analyst 39.
- `uv run poe eval --system agent --mode keyless --split dev`: both gates pass (safety 100%, grounding violations 0), labelled PLUMBING ONLY. Not committed as a result: it says nothing about quality.
- **Pending:** the live agent-vs-baseline run (needs Baron's OK).

### 2026-10-30: Phase 3 completed (live baseline cost-tracking run)

- Baron chose OpenAI, so I added `llm/openai.py` (Responses API structured outputs; D023), OpenAI prices (read 2026-10-30), `OPENAI_API_KEY`, and `--provider` / provider inferred from `--model`. Commit 6bdcc7d, 451 tests.
- Docker Desktop crashed at startup again (stale `Docker\run` sockets). The documented workaround fixed it; see Open issues.
- **Live baseline run (DoD item 5), approved by Baron:** `uv run poe eval --system baseline --mode live --split dev --limit 10 --model gpt-6-luna --confirm-live` → `eval/results/2026-10-30_baseline_live_dev_gpt-6-luna_n10_r1.md`.
  - 2026-10-30, `gpt-6-luna`, 10 dev questions, 1 repeat, 20 calls, commit 6bdcc7d, database unchanged.
  - Cost tracking verified: recorded $0.003076 equals the cost recomputed from the price table.
  - Tokens: 1,647 uncached input + 71,046 cached + 8,283 cache-write, 2,746 output. Prompt caching works: the first call wrote ~7.9k tokens and the next 9 questions each read 7,894 from the cache.
  - The estimate printed beforehand (≤ $0.0223) was conservative, because OpenAI counts the prompt at ~7.9k tokens vs the ~10.8k assumed.
  - Latency p50 6.6 s per question (2 calls).
  - **This is not an accuracy result.** The first 10 dev cases are the easy lookup/aggregation/join ones (EX lenient 10/10, strict 9/10; d010 added an extra `units_sold` column). Grounding violations 9/10 are expected: the baseline types numbers in free text.
- Phase 3 DoD: all five items pass.

### 2026-10-30: Phase 3 eval harness, golden set, baseline (in progress)

**Built**
- `eval/cases/dev.yaml` (40) and `eval/cases/test.yaml` (60):
  - all nine categories in both splits, 28% Indonesian;
  - every expected behaviour: answer, refuse_unsafe, refuse_unanswerable, state_assumption;
  - access-control cases asked by the Jakarta manager;
  - the planted-injection ticket in t055/t056.
  - Every gold SQL passes the validator and runs under its case's scope in ≤ 576 ms with < 1,000 rows. Every top-N gold was checked for ties at the cut-off (none).
- `eval/cases.py`: models, users → `UserScope`, `AS_OF_DATE` 2026-10-01.
- `eval/metrics.py`: EX strict/lenient (D019), grounding check, percentiles, mean ± std.
- `eval/systems.py` (`Prediction`, `GoldSystem`) and `eval/baseline.py`: single prompt with the whole dictionary (~10.8k tokens) → SQL → scoped executor → free-text answer; plus the keyless rule responder.
- `eval/run_eval.py`:
  - CLI `--system gold|baseline|agent --mode keyless|live --split dev[,test] --repeats --limit --model --confirm-live`;
  - repeats with mean ± std, safety gate, database fingerprint before and after;
  - JSON (every case) + markdown results in `eval/results/`, labelled SANITY CHECK / PLUMBING ONLY / LIVE.
- `eval/leakage.py` and `data/examples.yaml`: 28 few-shot examples. Closest example/eval question similarity is 0.78, under the 0.85 limit; no SQL is equal to a gold SQL.
- `backend/src/sql_analyst/llm/`: `base.py`, `pricing.py`, `fake.py`, `anthropic.py`, `factory.py`; settings `LLM_PROVIDER`, `LLM_MODEL`, `LLM_EFFORT`, `ANTHROPIC_API_KEY`. Moved forward from Phase 4 (D018).
- Tests (446 total):
  - `evaluation/test_cases_and_leakage.py`, `test_metrics.py`, `test_harness.py`: gold vs gold, the keyless run, the live guard with no network, every example SQL runs;
  - `unit/test_llm.py`: pricing, the fake, the Anthropic adapter against a stub.
- CI: gold-vs-gold and keyless plumbing eval steps.

**DoD evidence (2026-10-30, commit 074e2e0)**
- Gold vs gold EX = 100%: `eval/results/2026-10-30_gold_na_dev+test_na_n100_r1.md`. EX strict and lenient, valid SQL, refusal accuracy, and unsafe refusals are all 1.0 over 100 cases; the database is unchanged.
- Every gold SQL passes the validator: `test_every_gold_sql_passes_the_validator`, 79 cases.
- The keyless run completes and is labelled "PLUMBING ONLY": `eval/results/2026-10-30_baseline_keyless_dev_fake-keyless_n40_r1.md`. EX 0.0 is expected for a fake that sends one fixed query.
- The leakage test passes, and it was shown to catch a planted duplicate question and a copied gold SQL.
- `uv run poe check`: ruff clean, 71 files formatted, workflow schema valid, 446 passed.
- **Not done:** the live 10-question baseline (needs Baron's OK and the API key; see Next step).

**Decisions:** D017-D022 in `docs/DECISIONS.md`:
- fixed "today";
- the LLM layer built early;
- how EX is scored;
- what the safety and grounding metrics mean;
- `--confirm-live`;
- `eval/` layout.

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
