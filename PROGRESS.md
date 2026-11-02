# Progress

Updated by Claude at the end of every session. A fresh chat continues from here.

## Status

| Phase | Status | Notes |
|---|---|---|
| 0 Scaffold | **done** (2026-10-29) | all DoD items pass; see session log |
| 1 Synthetic enterprise database | **done** (2026-10-29) | all DoD items pass; see session log |
| 2 Safety layer | **done** (2026-10-29) | all DoD items pass; see session log |
| 3 Eval harness, golden set, baseline | **done** (2026-10-30) | all DoD items pass; see session log |
| 4 Agent core | **done** (2026-10-30) | all DoD items pass; see session log |
| 5 API | **done** (2026-10-30) | all DoD items pass; see session log |
| 6 Web app | **done** (2026-10-30) | all DoD items pass; see session log |
| 7 Real-mode evaluation | **done** (2026-11-02) | all DoD items pass; live model `gpt-6-luna` confirmed by Baron (D043) |
| 8 Deploy | not started | |
| 9 Portfolio packaging | not started | |

## Decided in the planning chat (2026-10-29)

- Project: an agentic NLQ / text-to-SQL analyst over a fictional Indonesian retailer (PT Arunika Niaga), English and Bahasa Indonesia.
- Stack: Python 3.12 + uv, LangGraph, FastAPI, PostgreSQL 16 + pgvector, sqlglot, fastembed, React + TypeScript + Vite.
- Four guarantees: read-only by construction, row-level security in Postgres, the model never types a number, shows its work.
- Build order: safety and evaluation before the agent.
- Provider-agnostic LLM interface; fake adapter for keyless tests and CI.

## Open questions for Baron

- Phase 8 (AWS EC2, Baron's choice on 2026-11-02): which instance (shared with the flagship or new, and its size; Postgres plus the embedding model need about 2 GB RAM), the domain or subdomain for HTTPS, and the daily budget cap for the public demo (suggested $1/day, the current default). An optional free keyless mirror (for example Render free plus Neon free with pgvector) comes after EC2 works; check current free-tier terms first.

## Open issues

- The first CI run on GitHub (run 41382216337, commit `78109c4`) hung in the Playwright smoke test after every other step passed; fixed in `390f95a` (D045); run 41386054419 on that commit is green. Run 1 may still show as running until GitHub's 6-hour job limit, unless Baron cancels it in the Actions tab.
- Local `web/node_modules` is incomplete: an `npm ci` on 2026-11-02 was blocked by a Vite dev server left running since 2026-10-30 (PID 32376, port 5173). Baron stops it, then runs `uv run poe web-install`. Until then `poe web-check` and `poe web-e2e` can't run locally.
- Rate limits live in memory in one API process (D032): fine for one container, not for several instances.
- Sessions are stateless JWTs: sign-out clears the cookie, but a copied token stays valid until it expires (8 h, D033).
- The function allow-list (D014) may refuse a legitimate function the agent needs; watch for `forbidden_function` errors in the Phase 3/4 eval and add functions deliberately.
- Gold SQL is Claude's reading of each question. Baron reviewed d019, d027, d029 on 2026-10-30 (D039, D040). The Phase 7 failures were read by hand (EVAL_RESULTS finding 6); t028's gold is one-row-two-columns, and EX can't match the same figures as two rows (D044).
- t056 (planted injection), checked by hand in Phase 7: every agent answer returns the hostile ticket subject as data, filled in by code; none follows it. Hardening idea: show text values from the database as quoted data in the answer, so the boundary is visible (EVAL_RESULTS finding 8).
- The no-data refusal rule (D040) over-fired once on test (t010, a partly covered year) and the agent once grouped by `region_id` for a city question (t018). Add dev cases for both before any fix (D044).
- The answer step writes its prompt to the cache and never reads it back (it contains the result rows): $0.0308 of the agent's $0.0856 on test. A cache-friendlier answer prompt is a possible saving, not measured.
- The embedding model downloads from Hugging Face on the first `index-build` (unauthenticated; ~220 MB). On Windows, huggingface_hub warns that symlinks are unsupported; the poe tasks silence the warning and caching still works.
- **Recurring (2026-10-29 and 2026-10-30):** Docker Desktop 4.80 on this machine crashed at startup because of leftover AF_UNIX socket files that Windows refuses to delete (error 1920). Workaround used on 2026-10-29: quit Docker Desktop and rename the folders aside: `%LOCALAPPDATA%\Docker\run` and `%LOCALAPPDATA%\docker-secrets-engine` (now `*.stale-20261029*`). They can be deleted after a reboot. If Docker fails to start again with "The file cannot be accessed by the system", repeat that. Quitting Docker Desktop normally (not killing it) should avoid it, but it happened again on 2026-10-30 after a normal session end (folders renamed to `*.stale-20261030`). The crash is in Docker's "Inference manager" (Docker Model Runner); turning that feature off in Docker Desktop settings may stop it. That is Baron's call, since it changes his Docker configuration.

## Next step

Phase 8: deploy to AWS EC2 (BUILD_GUIDE §13), only when Baron says so. Start with a plan; it needs his answers to the Phase 8 open questions above.

## Session log

_(newest first: date, what was done, decisions, issues)_

### 2026-11-02: published on GitHub

- Baron chose AWS EC2 for Phase 8, the public repository `Baron197/agentic-sql-analyst`, and the MIT license.
- **Before the push:** no secret in any commit (every real `.env` value checked against the whole history), `.env`, `runs/`, and `.cache/` gitignored, commits under the GitHub noreply address. MIT `LICENSE` added (`78109c4`).
- **First CI run:** the web job and every backend step passed, including `poe check`, the eval gates, and the keyless agent gate, but the Playwright smoke test never exited. Reproduced in the Linux Playwright image: the test passed in 2.9 s, then hung on teardown. Fix (D045): stop the web servers with SIGTERM; job and step timeouts so a hang fails in minutes. Verified in the same image: pass and exit in 7 s. The CI run on `390f95a` is green (the smoke step takes 6 s).

### 2026-11-01 to 2026-11-02: Phase 7 real-mode evaluation (completed)

- **Before the runs (dev only):** per-step usage and cache-hit rate in the harness, `prompt_cache_key` in the OpenAI adapter, and a dev check run (40 questions, $0.0244): EX relabeled 1.0.
- **Test runs** (60 questions × 3 repeats, approved budget $2 with a stop at 2× any estimate): agent, baseline, no-retrieval, no-repair, no-few-shot, and critic on `gpt-6-luna` (2026-11-01), and the agent on `gpt-4o-mini` (2026-11-02). Every run came in under its estimate. Total Phase 7 spend $0.6669. All safety gates passed and every run left the database unchanged.
- **Results** (docs/EVAL_RESULTS.md; every table generated by `eval/report.py` and linked to its file):
  - agent EX relabeled 0.933 ± 0.023 vs baseline 0.953 ± 0.031: within noise;
  - typed numbers: agent 0, baseline 48.3 per run;
  - ablations: null results;
  - critic: negative (0.873);
  - `gpt-4o-mini`: 0.733 at 1.6× the cost.
- **Decisions:** D041 (`prompt_cache_key` is a null result; the extra cost is the per-question retrieved context), D042 (two OpenAI models within budget), D043 (`gpt-6-luna`, confirmed by Baron; `LLM_MODEL` default changed, `LLM_PROVIDER` stays `fake`), D044 (no tuning after the test run; critic stays off).
- **DoD:**
  - every number in EVAL_RESULTS.md links to a results file (links checked);
  - the model choice is recorded in D043 with its reasoning and Baron's confirmation;
  - CI is still keyless: `poe check` and `poe web-check` pass with no key.
- **Also:** `eval/report.py` gained quality, cost, per-repeat, per-step, and language tables; ruff formatting fix.

### 2026-10-30: Scoring and refusal policy, decided with Baron (before Phase 7)

- **Review of the three dev failures shared by agent and baseline:** d019 and d027 had every number right but different labels (`False`/`True` vs `weekday`/`weekend`; `app` vs `Mobile app`). d029 ("penjualan bulan ini" on 2026-10-01) was refused by both because October 2026 has no data.
- **Baron's decisions:** different labels with the same meaning are acceptable; a period with no data should be refused, with follow-up questions offered.
- **Built:**
  - `ex_relabeled` (D039): a third EX score, with a "check by hand" list in every report. Re-scoring the committed Phase 4 runs offline, d019 and d027 now pass for both systems; the result files were not rewritten.
  - Follow-up suggestions on unanswerable refusals (D040), through the prompt, agent, API (`suggestions` in `/api/ask` and the stream's `answer` event), CLI, and web app (clickable chips). Keyless demo09 shows it. Kept only if the input guard accepts them and every year named is inside the data window.
  - Gold: dev d029 → `refuse_unanswerable`. The test split was scanned for period questions only; no test label changed (D040 lists the cases checked).
  - The input guard now catches "the email of every customer"-style requests (a gap found while testing).
- **Checks:** `REQUIRE_DB=1 uv run poe check` 741 passed; `uv run poe web-check` 25 passed and builds; the Playwright smoke test passes; gold-vs-gold on the updated gold is 100% on every EX score (`eval/results/2026-10-30_gold_na_dev+test_na_n100_r1_2.md`).

### 2026-10-30: Phase 6 web app (completed)

**Built** (`web/`, React 19 + TypeScript 6.0 + Vite 8 + Tailwind 4 + Recharts 3)
- Pages: sign-in (demo accounts listed; "Try as analyst / manager" buttons when `DEMO_LOGIN_ENABLED=true`), Ask, History (+ run detail), Data dictionary (searchable), About (how it works, the four guarantees, what this is and isn't). The fictional-data notice is in every page footer.
- Ask page:
  - demo questions from `/api/examples` and the question box (Enter to ask, 500-character counter);
  - a live step timeline from `/api/ask/stream` (fetch + SSE parser), announced to screen readers;
  - the answer card with "Numbers filled from the query result", assumption badges, caveats, and refusal reasons;
  - the auto chart (KPI / bar / line from the API's choice; Recharts loaded on demand, no animation);
  - the SQL panel (laid out by clause, copy button);
  - a sortable, paginated table with CSV download (formula-injection guard);
  - run details (model, tokens, cost, latency, repairs, keyless badge).
- Theme: Baron's portfolio colours and fonts (self-hosted, Latin subsets). Keyboard accessible (skip link, focus rings, labelled controls, `aria-sort`); loading, empty, and error states.
- API: `GET /api/auth/options` and `POST /api/auth/demo` (only with `DEMO_LOGIN_ENABLED=true`, D036), with 2 new tests.
- Tasks: `poe web-install`, `web`, `web-check`, `web-e2e`, `web-screenshots`. CI: a `web` job (lint, Prettier, typecheck, Vitest, build) and the Playwright smoke test in the backend job.

**Decisions:** D036 (one-click demo sign-in), D037 (toolchain; TypeScript pinned to 6.0 for typescript-eslint), D038 (the app follows the API's chart choice; no chart animation; CSV guard; SSE over fetch).

**Found and fixed while building:** descending sort put NULLs first (a Vitest test caught it); chart bars were captured half-drawn in a screenshot (animation now off); the email placeholder looked like a filled-in value.

**DoD evidence**
- `uv run poe web-check`: ESLint (0 warnings), Prettier, `tsc`, Vitest 24 passed (SSE parser incl. split UTF-8, CSV guard, SQL layout, run state, table sort/pagination, answer card, charts, Ask page with a mocked stream, sign-in errors and demo buttons), `vite build` OK (main bundle 93 kB gzipped, charts 107 kB loaded on demand).
- `uv run poe web-e2e`: the Playwright smoke test passes (sign in → ask a keyless demo question → steps, SQL, a 4-row table, and the answer appear). It runs against the Postgres container plus `poe api` and the Vite dev server; the fully containerised stack comes in Phase 8 (plan default 1).
- Streaming through the Vite proxy is incremental: with a cold API, the first `step` event arrived at 128 ms and the next at 1,654 ms (while the embedding model loaded), then the rest within 0.35 s.
- `REQUIRE_DB=1 uv run poe check`: 728 passed (726 before + 2 demo sign-in tests).
- Screenshots at 1280 px and 375 px: `docs/screenshots/ask-desktop-1280.png`, `ask-mobile-375.png`, `login-*.png`. Reviewed and approved by Baron on 2026-10-30 ("Looks good"); no changes requested.

### 2026-10-30: Phase 5 API (completed)

**Built**
- `api/`: `main.py` (app factory; executor, agent, and run store built once at startup; OpenAPI at `/api/docs`), `auth.py` (argon2id, JWT in an httpOnly SameSite=Lax cookie, scope loaded per request), `routes/` (auth, ask, runs, reference, ops), `streaming.py` (SSE: step…, sql, rows, answer, done / error), `deps.py` (kill switch → rate limit → budget), `ratelimit.py`, `store.py` (Postgres run store, spend, metrics), `logs.py` (JSON request logs; no question text or secrets), `models.py`.
- `Agent.stream()` (LangGraph `stream_mode="updates"`); a `RunSink` protocol so the CLI keeps JSONL and the API writes Postgres.
- `db/app.sql` + `db/app_setup.py` (`poe app-setup`): schema `app`, role `app_writer` (read users, append runs; nothing else), demo users seeded from `.env`. `db-reset` now runs it; `poe api` starts uvicorn.
- New settings and `.env.example` names: `APP_WRITER_PASSWORD`, `JWT_SECRET`, `DEMO_ANALYST_PASSWORD`, `DEMO_MANAGER_PASSWORD`, `SESSION_HOURS`, `COOKIE_SECURE`, `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD` (1.00), `LIVE_MODE_ENABLED` (false). Local values were generated into `.env` and never printed.
- CI: throwaway values for the new secrets and an `app-setup` step before the tests.

**Decisions:** D031 (app schema, write-only role), D032 (rate limits in memory; budget from stored runs), D033 (JWT cookie sessions), D034 (kill switch off by default), D035 (LangGraph updates + plain SSE). SECURITY.md has the API section and nine new threat rows mapped to tests.

**DoD evidence:** `REQUIRE_DB=1 uv run poe check`: 726 passed (684 before; 42 API tests in `backend/tests/api/`), lint, format, and workflow schema clean. Covered:
- auth required on every route but health and login, and wrong passwords rejected (same answer for an unknown email; lockout after 5 failures; forged, expired, unknown-user, and no-expiry tokens rejected): `test_auth.py`;
- RLS through the API: the Jakarta manager's answer and stream rows contain only Jabodetabek stores (20 vs the analyst's 39): `test_ask.py`;
- streaming event order: step × 9, sql, rows, answer, done; a refusal sends no sql/rows; a crash becomes an `error` event: `test_ask.py`;
- rate limit (429 with Retry-After, per user, shared by both ask routes), budget cap (429 with a seeded $5 run today), kill switch (503 with a live provider and `LIVE_MODE_ENABLED=false`, no model call made): `test_limits.py`;
- own runs only (another user's run is a 404), the run-store role cannot read data or change history, `app-setup` is idempotent: `test_runs_and_reference.py`.
- Test runs are deleted from `app.runs` after the session.

**Curl walkthrough** (`uv run poe api`, keyless mode; the password comes from `.env` and is not shown):

```
$ curl -s http://127.0.0.1:8000/api/health
{"status":"ok","database":true,"run_store":true,"mode":"keyless","live_mode_enabled":false}

$ curl -s -o /dev/null -w 'HTTP %{http_code}\n' -X POST http://127.0.0.1:8000/api/ask -H 'Content-Type: application/json' -d '{"question":"How many orders?"}'
HTTP 401


$ curl -s -w '  HTTP %{http_code}\n' -X POST http://127.0.0.1:8000/api/auth/login -H 'Content-Type: application/json' -d '{"email":"manager.jakarta@demo","password":"wrong"}'
{"detail":{"code":"bad_credentials","message":"Wrong email or password."}}  HTTP 401


$ curl -s -c cookies.txt -X POST http://127.0.0.1:8000/api/auth/login -H 'Content-Type: application/json' -d '{"email":"manager.jakarta@demo","password":"'"$DEMO_MANAGER_PASSWORD"'"}'
{"user_id":"manager.jakarta@demo","display_name":"Demo manager (Jakarta)","role":"manager","region_ids":[1,2,3,4,5]}

$ curl -s -b "cookies.txt" -X POST http://127.0.0.1:8000/api/ask -H 'Content-Type: application/json' -d '{"question":"How many orders did each store get in September 2026?"}' | uv run python -c "import json,sys; d=json.load(sys.stdin); print(json.dumps({k: d[k] for k in ('status','answer','row_count','assumptions','usage')}, indent=1)); print('first rows:', d['rows'][:3])"
{
 "status": "answered",
 "answer": "In September 2026, Arunika Jakarta Senayan received the most orders (78). The 20 stores you can see received 1,046 orders in total.",
 "row_count": 20,
 "assumptions": [
  "Counts all orders placed in September 2026 (WIB), including cancelled ones."
 ],
 "usage": {
  "model": "fake-keyless",
  "keyless": true,
  "llm_calls": 2,
  "input_tokens": 5178,
  "cache_read_tokens": 0,
  "output_tokens": 171,
  "cost_usd": 0.0,
  "latency_ms": 1551.9,
  "repairs": 0
 }
}
first rows: [['Arunika Jakarta Senayan', 78], ['Arunika Bogor Pajajaran', 68], ['Arunika Jakarta Cempaka Putih', 57]]


$ curl -s -N -b "cookies.txt" -X POST http://127.0.0.1:8000/api/ask/stream -H 'Content-Type: application/json' -d '{"question":"Metode pembayaran apa yang paling sering dipakai pada tahun 2026?"}' | cut -c1-150
event: step
data: {"node":"guard_input","status":"done","ms":0.0,"note":null}

event: step
data: {"node":"retrieve_context","status":"done","ms":19.8,"note":"9 views, 0 values, 4 examples"}

event: step
data: {"node":"generate_sql","status":"done","ms":0.4,"note":"confidence high"}

event: step
data: {"node":"validate_sql","status":"done","ms":2.4,"note":"fact_payments"}

event: step
data: {"node":"execute","status":"done","ms":49.9,"note":"6 rows, cost 2,190"}

event: step
data: {"node":"check_result","status":"done","ms":0.0,"note":"ok"}

event: step
data: {"node":"write_answer","status":"done","ms":0.1,"note":null}

event: step
data: {"node":"render_numbers","status":"done","ms":0.1,"note":"grounded"}

event: step
data: {"node":"finalize","status":"done","ms":3.0,"note":"answered"}

event: sql
data: {"sql":"SELECT p.payment_method, COUNT(*) AS payments FROM analytics.fact_payments AS p WHERE CAST((p.paid_at AT TIME ZONE 'Asia/Jakarta') AS DA

event: rows
data: {"columns":["payment_method","payments"],"rows":[["ewallet",2354],["card",1946],["qris",1934],["cash",1224],["bank_transfer",919],["cod",665]],"

event: answer
data: {"status":"answered","text":"Pada tahun 2026, metode yang paling sering dipakai adalah ewallet (2.354 pembayaran), diikuti card (1.946).","assum

event: done
data: {"run_id":"9aca37ecf548491b86016fb8473a4286","usage":{"model":"fake-keyless","keyless":true,"llm_calls":2,"input_tokens":5671,"cache_read_tokens



$ curl -s -b "cookies.txt" 'http://127.0.0.1:8000/api/runs?limit=2'
{"runs":[{"run_id":"9aca37ecf548491b86016fb8473a4286","created_at":"2026-10-30T05:06:32.625627Z","status":"answered","question":"Metode pembayaran apa yang paling sering dipakai pada tahun 2026?","model":"fake-keyless","keyless":true,"cost_usd":0.0,"elapsed_ms":82.0},{"run_id":"708e440771744ab5b07286df2b09c13e","created_at":"2026-10-30T05:06:32.446604Z","status":"answered","question":"How many orders did each store get in September 2026?","model":"fake-keyless","keyless":true,"cost_usd":0.0,"elapsed_ms":1551.9}]}

$ curl -s -b "cookies.txt" http://127.0.0.1:8000/api/metrics
{"runs":4,"failed_runs":0,"latency_p50_ms":819.4,"latency_p95_ms":1714.1,"cost_today_usd":0.0,"runs_today":4,"cache_read_tokens":0,"keyless_runs":4,"error_rate":0.0,"cache_hit_rate":0.0,"daily_budget_usd":1.0,"mode":"keyless"}
```

### 2026-10-30: Phase 4 completed (live agent-vs-baseline run on dev)

- **Live runs, approved by Baron** (estimate printed beforehand: agent ≤ $0.19, baseline ≤ $0.09):
  - `uv run poe eval --system agent --mode live --split dev --model gpt-6-luna --confirm-live` → `eval/results/2026-10-30_agent_live_dev_gpt-6-luna_n40_r1.md`
  - `uv run poe eval --system baseline --mode live --split dev --model gpt-6-luna --confirm-live` → `eval/results/2026-10-30_baseline_live_dev_gpt-6-luna_n40_r1.md`
  - Both: 2026-10-30, `gpt-6-luna`, 40 dev questions, 1 repeat, commit a8f4379, database unchanged. Recorded costs equal the costs recomputed from the price table.
- **Comparison (dev is the tuning split: one repeat, not a reportable accuracy number):**

  | Metric | Agent | Baseline |
  |---|---|---|
  | EX strict | 0.697 | 0.697 |
  | EX lenient | 0.879 | 0.909 |
  | Valid SQL rate | 0.970 | 0.970 |
  | Repair rate | 0.0 | n/a |
  | Refusal accuracy / unsafe refusal rate | 1.0 / 1.0 | 1.0 / 1.0 |
  | Safety block rate (gate) | 1.0 | 1.0 |
  | Grounding violations (agent gate) | **0** of 32 answers | 31 of 32 answers |
  | Latency p50 / p95 | 9.2 s / 13.1 s | 6.2 s / 10.3 s |
  | Cost, 40 questions | $0.0241 | $0.0120 |

- **Honest reading:** on dev the agent does **not** beat the baseline on accuracy. It ties on strict EX and is one case behind on lenient EX, at about twice the cost and 1.5× the latency. What it adds is the grounding guarantee (0 vs 31 of 32 answers with model-typed numbers) with no loss of safety. On a 22-view schema the whole dictionary fits in a cached prompt, so the baseline is strong. Whether retrieval or repair help is for the Phase 7 ablations on the test split, with 3 repeats.
- Failures, agent: d019 and d027 (the baseline fails them too: worth a gold spot-check), d028 (a 12-month window for "best customers", steered by an example in my SQL prompt; the baseline got it right), d029 (both refused an ambiguous "this month" question). No run needed a repair.
- **Fixed after the run** (the committed results show the problem as it was):
  - the model wrote "Rp"/"IDR" next to money slots, which rendered as "RpRp 8,81 miliar" and "IDR 1.24B IDR". Code now drops a currency word next to a money slot, and the answer prompt says money slots carry their currency. Regression test in `test_render.py`;
  - the SQL prompt's example assumption ("best customers = … last 12 months") resembled dev d028 and steered it. It's replaced with a neutral example.
  - Neither change affects the scored metrics (EX and grounding are scored on SQL results and model-typed text). Not re-run, to avoid spending without a new OK.
- Total live spend this session: $0.0361.
- Phase 4 DoD: all four items pass. `REQUIRE_DB=1 uv run poe check`: 684 passed.

### 2026-10-30: Phase 4 agent core (built and tested keylessly)

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
- The live agent-vs-baseline run followed in the next session-log entry.

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
