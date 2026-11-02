# Design decisions

Short entries, newest last: context, decision, why, alternatives considered.

## D001: Python package lives in `backend/src`, built with `uv_build` (2026-10-29, Phase 0)

- **Context:** BUILD_GUIDE §5 puts `pyproject.toml` at the repo root and the package in `backend/src/sql_analyst`.
- **Decision:** one root `pyproject.toml` using uv's own build backend with `module-root = "backend/src"`.
- **Why:** a single lockfile and virtualenv for backend, eval, and CI; `uv_build` needs no extra tool and supports a non-default source root.
- **Alternatives:** hatchling (works, one more dependency); a separate `backend/pyproject.toml` (two places to run commands from).

## D002: Python pinned to 3.12 (2026-10-29, Phase 0)

- **Context:** the machine has Python 3.15 installed via uv; the guide specifies 3.12.
- **Decision:** `requires-python = ">=3.12,<3.13"` plus `.python-version`; uv installs 3.12 itself.
- **Why:** follow the spec; 3.12 has wheels for every planned dependency (psycopg, fastembed/onnxruntime, sqlglot). Revisit only if a dependency needs newer.
- **Alternatives:** `>=3.12` unbounded (risks the lockfile resolving for versions we never test).

## D003: CI workflow validated with `check-jsonschema`, not `actionlint` (2026-10-29, Phase 0)

- **Context:** Phase 0 DoD needs "the CI YAML is valid", checkable locally.
- **Decision:** `uv run poe lint-ci` runs `check-jsonschema --builtin-schema vendor.github-workflows`, and it is part of `poe check`.
- **Why:** pure Python, installed by `uv sync`, works offline (the SchemaStore schema is vendored in the package).
- **Alternatives:** `actionlint` (deeper checks such as expression typing, but a Go binary to download and keep updated). Can be added later.

## D004: Database tests skip locally, fail in CI (2026-10-29, Phase 0)

- **Context:** some tests need the Postgres container; contributors may run `poe check` without Docker.
- **Decision:** tests marked `db` are skipped when Postgres is unreachable, unless `REQUIRE_DB=1`, which CI sets.
- **Why:** a quick local check without Docker, while CI can never go green by silently skipping database tests.
- **Alternatives:** always require Docker (slower inner loop); always skip when down (CI could hide a broken database).

## D005: Local dev database bound to 127.0.0.1, password required from `.env` (2026-10-29, Phase 0)

- **Context:** the compose database holds the owner role.
- **Decision:** the port is published on 127.0.0.1 only, and compose fails fast (`${POSTGRES_PASSWORD:?…}`) if no password is set. No default password exists anywhere in the repo; CI uses a throwaway value for its disposable service container.
- **Why:** avoids exposing a superuser on the LAN and avoids a well-known default password.
- **Alternatives:** a default `postgres/postgres` (convenient, but a bad habit to show in a security-first project).

## D006: Connect to `127.0.0.1`, not `localhost` (2026-10-29, Phase 1)

- **Context:** the first full `db-load` took 271 s. Profiling showed the load itself took about 10 s; each new connection took 130 s. On this Windows machine `localhost` resolves to `::1` first, and Docker Desktop's port forward hangs on IPv6 until the TCP timeout before psycopg falls back to IPv4.
- **Decision:** `POSTGRES_HOST` defaults to `127.0.0.1` in `config.py`, `.env.example`, and CI. Compose already publishes the port on `127.0.0.1` only (D005).
- **Why:** connect time went from 130 s to 0.01 s, and `db-reset` from 4 m 35 s to about 15 s.
- **Alternatives:** publish the port on `::1` too (still slow if anything else claims it); set `connect_timeout` (hides the problem and still wastes seconds per connection).

## D007: Inventory snapshots cover the last 183 days only (2026-10-29, Phase 1)

- **Context:** daily stock for every store × product × day over 33 months would be about 10M rows and break the 2-minute rebuild budget.
- **Decision:** `fact_inventory_daily` covers 1 Apr - 30 Sep 2026 (about 890k rows, each store carrying ~55% of the range). Documented in the dictionary and DATA.md, so questions about older stock can be answered with "no data".
- **Why:** keeps realistic daily granularity (stock-outs, reorder points) and a fast rebuild.
- **Alternatives:** weekly snapshots for the full range (coarser, less realistic for "days out of stock").

## D008: Seed generator in pure Python with per-domain string-seeded RNGs (2026-10-29, Phase 1)

- **Context:** the data must be identical on every rebuild (checksum DoD) and still realistic.
- **Decision:** one `random.Random("42:<domain>")` per domain (sales, customers, inventory, …) and one seeded Faker per domain. No set iteration over strings anywhere. Rows go in with Postgres `COPY`; foreign keys are added after the load so a broken seed fails the rebuild.
- **Why:** string seeds are hashed with SHA-512, so output does not depend on `PYTHONHASHSEED` (tested in two subprocesses); per-domain RNGs mean changing one generator does not reshuffle the others. Generation takes about 4-6 s, so numpy is unnecessary.
- **Alternatives:** numpy (faster, but a large dependency for no gain here); a single global RNG (any change shifts every table).
- **Caveat:** Faker output may change between versions; `uv.lock` pins it.

## D009: Metric definitions in the glossary (2026-10-29, Phase 1)

- **Context:** the guide names the metrics but not every edge case.
- **Decision:**
  - net revenue = line value after line discounts, minus refunds, excluding cancelled orders; refunds are attributed to the order's date; shipping fees are not revenue;
  - AOV uses `total_amount` (after discounts, before refunds);
  - active customers = registered customers with ≥1 completed order in the 90 days up to the last order date in the data;
  - conversion rate = converted website/app sessions ÷ all sessions (marketplace and stores excluded).
- **Why:** each is a common retail definition, and stating the choice in the dictionary is what lets the agent (and the eval) be consistent.
- **Alternatives:** attributing refunds to the return date (better for cash accounting, but then a month's revenue changes after it closes).

## D010: Personal data stays in `core`; analytics omits it rather than masking it (2026-10-29, Phase 1)

- **Context:** the guide asks for masked views in Phase 2.
- **Decision:** in Phase 1, analytics views simply leave out names, emails, phones, addresses, birth dates, gender, salaries, and supplier contacts (employee names too). The dictionary model already has a `pii` flag, so Phase 2 can add masked columns and the validator can reject them.
- **Why:** nothing the agent needs to answer business questions requires personal data.
- **Alternatives:** masked columns now (more surface before the safety layer exists).

## D011: `db-reset` keeps the volume; `db-wipe` deletes it (2026-10-29, Phase 1)

- **Context:** in Phase 0, `db-reset` dropped the Docker volume. Phase 1 needs a rebuild that also works against CI's service container.
- **Decision:** `db-load` drops and recreates the `core` and `analytics` schemas on whatever database `.env` points at; `db-reset` = `db-up` + `db-load`; `db-wipe` = `docker compose down -v`.
- **Why:** faster, and one code path for local and CI. Cluster-level roles from Phase 2 survive a reset.
- **Alternatives:** always recreate the container (slower, and impossible in CI).

## D012: Row-level security on `core` tables for the views' owner (2026-10-29, Phase 2)

- **Context:** the guide asks for "policies on region-scoped views", but Postgres row-level security applies only to tables. A view reads its base tables with its owner's privileges.
- **Decision:** policies live on the `core` tables and target `analytics_owner`, a `NOLOGIN`, non-`BYPASSRLS` role that owns every analytics view. Child tables reach their region through `SECURITY DEFINER` set-returning functions (`rls.visible_stores()`, `rls.visible_orders()`, …), which the planner runs once per query as a hashed subplan.
- **Why:** everyone reading the views is scoped, the admin role included, and the agent role never needs access to `core`. Heaviest scoped query measured: 238 ms.
- **Alternatives:** `security_invoker` views (PG15+) would make `nlq_reader` need `SELECT` on `core`; security-barrier views with a `WHERE` filter put the rule in the view text rather than in Postgres RLS.

## D013: The region scope is HMAC-signed (2026-10-29, Phase 2)

- **Context:** with the guide's plain `SET LOCAL app.region_ids`, SQL that slipped past the validator could call `set_config('app.region_ids', 'all', true)` and see every region. The database would not stop it.
- **Decision:** the executor also sets `app.region_sig = HMAC-SHA256(key, region_ids | backend pid | transaction start)`. `rls.verified_scope()` recomputes it with a key in `rls.signing_key` that no query role can read. A missing, forged, widened, or replayed scope sees zero rows. The key comes from `RLS_SIGNING_KEY` and is loaded by `db-load`.
- **Why:** "row-level security enforced by Postgres" then holds even with the validator bypassed (tested), and the design fails closed.
- **Alternatives:** a login role per region or `SET ROLE` per request (more roles to manage; `RESET ROLE` needs the same protection); trusting the validator alone (one layer).

## D014: Function allow-list plus deny-list (2026-10-29, Phase 2)

- **Context:** the guide specifies a function deny-list. Postgres has hundreds of built-in functions, and a deny-list only blocks the ones someone thought of.
- **Decision:** functions sqlglot does not model (they parse as `Anonymous`, which covers every Postgres admin, file, and config function) must be on an allow-list of analytics functions. Every function, typed or not, is also matched against a deny-list regex.
- **Why:** an unknown function is refused by default. The cost is that a harmless but unusual function may be refused; that shows up as a validator error, never a leak, and is fixed by adding it to the list.
- **Alternatives:** deny-list only (the guide's design).

## D015: The executor runs SQL regenerated from the AST (2026-10-29, Phase 2)

- **Context:** if the validator and Postgres parse the same text differently (comments, quoting), the validator can approve something other than what Postgres runs.
- **Decision:** `ValidatedSQL.sql` is `stmt.sql(dialect="postgres", comments=False)`, and only that string is sent to the database, wrapped as `SELECT * FROM (…) AS _q LIMIT 1001`.
- **Why:** Postgres sees exactly the tree that was validated, with no comments. All 21 must-pass queries, including the glossary SQL, run correctly after regeneration (tested for both scopes).
- **Alternatives:** run the original text (simpler, but open to parser differentials).

## D016: "Jakarta manager" = the Jabodetabek region group; cost limit 250,000 (2026-10-29, Phase 2)

- **Context:** the guide's demo manager sees "Jakarta region only". The dictionary defines `region_group` as the management reporting unit. Separately, the cost guard needs a number.
- **Decision:** the manager's scope is region IDs 1-5 (Jakarta, Bogor, Depok, Tangerang, Bekasi). The planner-cost limit is 250,000, calibrated in docs/SECURITY.md: about 8× the heaviest legitimate query (29,598), below every large cross join (317k-73M).
- **Why:** a regional manager manages a region group, not a single city. The cost limit separates the measured legitimate and accidental queries by a wide margin.
- **Alternatives:** Jakarta city only (region 1); a higher cost limit relying on the 5 s timeout alone.

## D017: Eval questions use a fixed "today" of 2026-10-01 (2026-10-30, Phase 3)

- **Context:** questions like "last month" or "bulan lalu" depend on the current date, but the data ends on 2026-09-30 and eval results must be reproducible.
- **Decision:** the harness tells every system that today is 2026-10-01 (`eval/cases.py` `AS_OF_DATE`). Gold SQL uses literal dates. "Last month" means September 2026, and "this month" (October 2026) has no data, which makes it an ambiguous case.
- **Why:** the results never change with the calendar, and the anchor sits right after the data, as a real "today" would.
- **Alternatives:** use the real date (results drift, and most relative windows would be empty).

## D018: The LLM interface and the Anthropic adapter are built in Phase 3, not Phase 4 (2026-10-30, Phase 3)

- **Context:** the Phase 3 DoD includes a live baseline run, which needs a real model call. The guide puts the adapters in Phase 4.
- **Decision:**
  - build `llm/base.py` (interface + `Usage`), `pricing.py`, `fake.py`, `anthropic.py`, and `factory.py` now;
  - the Anthropic adapter uses `client.messages.parse(output_format=PydanticModel)` (structured outputs), puts `cache_control` on the system prompt, and sends no `temperature` and no prefill;
  - it raises `LLMRefusal` / `LLMError` (with usage) on `refusal`, `max_tokens`, or a missing parsed output.
- **Why:** Baron chose Anthropic for the live baseline. The interface is provider-agnostic, so OpenAI and Azure are later adapters (S4).
- **Not done yet:** server-side refusal fallbacks (`fallbacks: "default"`) apply to Sonnet 5.5 and Opus 5.5, not Haiku 5.5. Add them if Phase 7 picks one of those models.
- **Prices:** `pricing.py` holds Anthropic list prices as of 2026-10-06, including the Haiku 5.5 long-prompt rate card (> 100K tokens) and per-model cache read/write rates. An unknown model raises an error instead of costing $0.

## D019: How execution accuracy is scored (2026-10-30, Phase 3)

- **Context:** EX compares the prediction's result with the gold result. Naive comparisons fail on harmless differences (column order and names, `0.04298` vs `0.0430`, `3480887.43` vs `3480887`).
- **Decision:**
  - rows are compared as multisets (as ordered lists if `order_matters`);
  - column names and order are ignored: each gold column is matched to a predicted column by its values;
  - *strict* = the same set of columns; *lenient* = the gold columns are a subset of the predicted ones;
  - predicted numbers are rounded to the gold column's precision;
  - a truncated (row-capped) prediction counts as wrong, and a refusal on an answerable case counts as wrong.
  - Gold SQL selects only what the question asks for and rounds averages and ratios, so lenient scoring has a clean target.
- **Why:** this matches what a human would accept as "the same answer" without hiding real errors (a total that is off by one rupiah still fails; tested).
- **Alternatives:** exact comparison with column order (Spider/BIRD style), which penalises presentation rather than correctness.

## D020: What the safety and grounding metrics mean (2026-10-30, Phase 3)

- **Context:** writes and out-of-scope rows are already impossible by construction (Phase 2), so a "safety block rate" could look like a trivially perfect number.
- **Decision:**
  - `safety_block_rate` (the gate, must be 100%) counts adversarial and access-control cases where nothing unsafe reached the data: every query went through the validated, read-only, row-level-secured executor, and the database fingerprint is unchanged after the run;
  - `unsafe_refusal_rate` separately measures whether the system *politely refused* unsafe requests, a quality number;
  - `grounding_violations` counts answers containing a number that does not appear in the question (guarantee 3). It is a gate for the agent only. The baseline writes free text, so it is expected to violate it, and that contrast is the point.
- **Why:** each number is honest about what it measures. A gate over zero relevant cases is labelled as such instead of passing silently.
- **Not done yet:** whether an answer *repeats* the planted injection (case t056) is checked by hand until the Phase 4 templates make it testable.

## D021: Live eval runs need `--confirm-live` (2026-10-30, Phase 3)

- **Context:** CLAUDE.md requires Baron's OK and a cost estimate before any paid API call.
- **Decision:** `--mode live` prints the model, the number of calls, and an upper-bound cost estimate, then exits with code 3 unless `--confirm-live` is given (tested without any network call). Keyless is the default.
- **Why:** an accidental `poe eval --mode live` costs nothing.
- **Alternatives:** an interactive prompt (doesn't work in CI or scripts).

## D022: Eval code lives in the top-level `eval/` package (2026-10-30, Phase 3)

- **Context:** BUILD_GUIDE §5 puts `run_eval.py`, `metrics.py`, `baseline.py`, and the cases under `eval/`, outside the installable package.
- **Decision:** `eval/` is a plain package imported from the repo root (`python -m eval.run_eval`; pytest `pythonpath = ["."]`). Its tests live in `backend/tests/evaluation/`, named so they can't shadow the `eval` package.
- **Why:** follows the guide's layout. The harness is a development tool, not part of the deployed app.
- **Alternatives:** move it into `sql_analyst/evaluation/` (one package, but it diverges from the guide).

## D023: OpenAI adapter for the live baseline run (2026-10-30, Phase 3)

- **Context:** Baron has an OpenAI API key and asked to use OpenAI for the live baseline run instead of Anthropic. BUILD_GUIDE §8.3 lists OpenAI as one of the live providers.
- **Decision:**
  - `llm/openai.py` uses the Responses API, `client.responses.parse(text_format=PydanticModel)` (structured outputs, checked against the installed `openai` 3.41.0), with the system prompt in `instructions`, `store=False`, and no `temperature`;
  - OpenAI's `input_tokens` includes cached tokens, so uncached = input − cached;
  - cost is computed from the requested model id (the response may carry a dated snapshot id);
  - `incomplete` responses and refusals raise `LLMError` / `LLMRefusal` with the usage attached;
  - the harness infers the provider from `--model` (`gpt-*` → openai, `claude-*` → anthropic) or takes `--provider`.
- **Prices:** OpenAI standard tier, read from developers.openai.com/api/docs/pricing on 2026-10-30: `gpt-4o-mini` $0.15 / $0.60 (cached $0.075); `gpt-6-luna` $0.10 / $0.50 (cached $0.01); `gpt-5-mini` $0.25 / $2.00. The page lists no cache-write price, so writes are assumed to cost the normal input rate.
- **Why:** the interface stays provider-agnostic, so the Anthropic adapter stays and the final model choice is still Phase 7.

## D024: Multilingual embedding model instead of a small English BGE (2026-10-30, Phase 4)

- **Context:** BUILD_GUIDE §4 suggests a small BGE model with fastembed. About a third of the questions (and the dictionary synonyms) are in Bahasa Indonesia; the English BGE models embed it poorly.
- **Decision:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` through fastembed 0.9.1 (ONNX, 384 dimensions, ~220 MB, Apache-2.0), cached in `.cache/fastembed` (gitignored; cached in CI). Unit tests use a hashing embedder, so they need no download.
- **Why:** still local, keyless, and free; handles both languages with one index.
- **Alternatives:** `BAAI/bge-small-en-v1.5` (67 MB, English only); `intfloat/multilingual-e5-large` (2.2 GB, too heavy for CI and a small server).

## D025: Retrieval index in pgvector, in its own `retrieval` schema (2026-10-30, Phase 4)

- **Context:** the agent needs vector search over ~217 chunks (22 views, 161 columns, 6 metrics, 28 examples) plus ~650 categorical values.
- **Decision:**
  - `poe index-build` (run after `db-load`; `db-reset` now does both) creates schema `retrieval` with pgvector installed into it and tables `chunks`, `column_values`, `meta`;
  - the agent reads it as `nlq_reader` (`USAGE` + `SELECT` only), with fixed queries written by code;
  - BM25 (rank-bm25) runs in memory over the same chunks; the two rankings are fused by RRF (k = 60);
  - the index records its embedding model, and the agent refuses to start against an index built with a different one.
- **Why:** follows the guide's architecture (vectors in Postgres). Model-written SQL still cannot read the index: the validator allows `analytics` views only (new adversarial cases).
- **Alternatives:** an in-memory index only (simpler, but drops pgvector); a separate role for retrieval reads (more moving parts for non-sensitive data).
- **Note:** the values cover all regions. They are dimension names (cities, stores, categories), not personal data; the rows behind them stay protected by row-level security (docs/SECURITY.md).

## D026: Value matching and join bridging rules (2026-10-30, Phase 4)

- **Decision:**
  - value matching uses rapidfuzz on 1-4 word phrases of the question. Phrases of three characters or fewer must match exactly ("Jkt" → `city_code` JKT). Single words must match a whole value. Multi-word phrases may match part of a value ("Gading Serpong" → the store "Arunika Tangerang Gading Serpong"). Values of deprecated columns (`fact_orders.region_code`) are never suggested;
  - after picking the top views, retrieval adds every view on any shortest join path between them. When paths tie (orders reach regions through the store, the customer, or the shipment destination), all of them are added, and the business rules say which one to use.
- **Why:** these rules came from checking the dev questions by hand; earlier versions matched "store" to every store or nudged the model towards the deprecated column.

## D027: Grounding is scored on the text the model typed (2026-10-30, Phase 4)

- **Context:** guarantee 3: every number in an answer comes from the query. The rendered answer naturally contains numbers (code put them there), so checking it would flag every correct answer.
- **Decision:**
  - the model writes a template; `render_numbers` rejects it if the template without its slots, or its caveats, contain a number that is not in the question;
  - the eval scores the same text (`Prediction.model_text`), using the same function (`agent/grounding.py`, re-exported by `eval/metrics.py`); for the baseline the whole free-text answer is model-typed;
  - assumptions keep a figure only if it also appears in the question or the executed SQL (dates and limits the query uses); others are dropped;
  - refusal messages are written by code, and the model's refusal reason is shown separately as the model's note, not as the answer.
- **Why:** the check measures exactly what the guarantee promises, with one definition shared by the agent and the scorer.
- **Alternatives:** checking the rendered answer minus filled values (fragile with formatting); no check on assumptions (would let figures through a side door).

## D028: Ablation switches; critic and LLM guard off by default (2026-10-30, Phase 4)

- **Decision:** `AgentConfig` has `retrieval`, `repair`, `few_shot`, `critic`, `guard_llm`; the harness exposes `--ablation no-retrieval,no-repair,no-few-shot` and `--critic`, and names the result file after the variant (for example `agent-no-retrieval`). The no-retrieval variant puts the whole dictionary in the static prompt, like the baseline, with no value matches or examples.
- **Why:** BUILD_GUIDE §8.2 and §9 say the critic's value must be measured, not assumed. Both optional LLM calls add cost and latency, so they start off and Phase 7 measures them.

## D029: Budget, repair, and fallback semantics (2026-10-30, Phase 4)

- **Decision:**
  - limits per run (settings): 8 LLM calls, 60,000 tokens, $0.05, 60 s;
  - the call limit is checked before entering a node that calls the model, so a run never exceeds it; the others are checked after each node;
  - repairs are capped at 3 (validator error, database error, or a suspicious result). `check_result` may send a run back once; after that an empty or odd result is accepted with a caveat. If a retry it asked for fails with no repairs left, the earlier result is answered with a caveat;
  - `write_answer` retries once after a rejected template, then the answer is the table with a code-written sentence;
  - a budget stop ends with status `partial` and returns the table if a query ran.
- **Why:** every failure path ends in a defined state that still shows the user something verifiable.

## D030: Keyless demo mode and the run store (2026-10-30, Phase 4)

- **Decision:**
  - `data/demo.yaml` holds 8 demo questions (6 answers in English and Indonesian, 2 unsafe). In keyless mode the fake model replays their SQL and templates; retrieval, validation, the read-only executor, row-level security, and rendering all run for real. Other questions are declined in the CLI; eval plumbing runs use one canned query instead, so every step is exercised;
  - the demo questions go through the same leakage guard as the few-shot examples;
  - runs are appended to `runs/<date>.jsonl` (gitignored, 50 rows kept per run). Phase 5 moves them to Postgres, written by a separate role, so `nlq_reader` stays read-only.
- **Why:** anyone can run the agent with no API key, and keyless output is labelled so it is never mistaken for model quality.

## D031: The API's own schema and a write-only login (2026-10-30, Phase 5)

- **Context:** the API must store users and runs, but the agent's login must stay read-only (CLAUDE.md hard rule).
- **Decision:**
  - schema `app` (`users`, `runs`) and role `app_writer`: `SELECT` on `app.users`, `SELECT, INSERT` on `app.runs`; no update or delete, no access to the data schemas;
  - `poe app-setup` creates both and seeds the demo users from `.env`. It is idempotent and `db-load` doesn't touch `app`, so stored runs survive a data reload. `db-reset` runs it last;
  - the CLI keeps the JSONL run store; the API passes its Postgres store to the agent's `finalize` node.
- **Why:** each login can do exactly one job. A bug in the API can't change the data, and a bug in the agent can't rewrite history.
- **Alternatives:** the admin role for the API (far too much power); runs as files (no per-user queries, lost on redeploy).

## D032: Rate limits in memory, budget from stored runs (2026-10-30, Phase 5)

- **Decision:**
  - per-user question limit (10/min) and sign-in lockout (5 failures/min/email) use an in-memory sliding window per process;
  - the daily budget sums `app.runs.cost_usd` since midnight WIB and is checked before every question;
  - order of checks: kill switch (503), rate limit (429), budget (429).
- **Why:** the deploy target is one container, where in-memory counts are exact and need no extra service. The budget reads the database, so it holds across restarts.
- **Limits:** several API instances would each count separately (move the counts to Postgres or Redis then); runs in flight when the budget is reached still finish, so the cap can be overshot by one run's budget per question in flight.

## D033: Sessions are JWTs in an httpOnly cookie (2026-10-30, Phase 5)

- **Decision:** HS256 JWT with only `sub`, `iat`, `exp` (8 h), in an `httpOnly`, `SameSite=Lax` cookie, `Secure` behind HTTPS (`COOKIE_SECURE`). The scope is loaded from `app.users` per request. Sign-out clears the cookie (stateless: no revocation list).
- **Why:** BUILD_GUIDE §10. Scripts can't read the token, cross-site posts don't carry it, and a changed scope applies on the next request.
- **Alternatives:** server-side sessions (revocable, but one more table and a lookup per request; worth it only with real accounts).

## D034: The kill switch is off by default (2026-10-30, Phase 5)

- **Decision:** `LIVE_MODE_ENABLED=false` is the default. With a paid provider configured, `/api/ask` and `/api/ask/stream` then return 503 before any model call. Keyless mode ignores the switch.
- **Why:** a deploy that picks up an API key by mistake still can't spend money until someone turns live mode on deliberately.

## D035: Streaming with LangGraph updates and plain SSE (2026-10-30, Phase 5)

- **Decision:** `Agent.stream()` uses LangGraph's `stream_mode="updates"` and yields each node's timing as the node finishes; `api/streaming.py` formats server-sent events by hand and FastAPI's `StreamingResponse` sends them. A run that ends with status `error`, or a crash mid-stream, becomes an `error` event (the HTTP status is already 200).
- **Why:** no extra dependency (sse-starlette), and the step events arrive live rather than all at the end.
- **Note:** the request log line for a stream is written when the headers go out; a separate "ask finished" line carries the run id and status.

## D036: One-click demo sign-in instead of printing demo passwords (2026-10-30, Phase 6)

- **Context:** BUILD_GUIDE §10-11 says the public demo shows the demo credentials on the sign-in page.
- **Decision:** `GET /api/auth/options` lists the demo accounts (emails and roles). With `DEMO_LOGIN_ENABLED=true` (public demo only; default false), `POST /api/auth/demo {"user": "analyst" | "manager_jakarta"}` signs in as that seeded user, and the page shows "Try as analyst / manager" buttons. The normal password sign-in stays.
- **Why:** visitors get the same one-click access, and the demo passwords never appear in the page, the JavaScript bundle, or screenshots. The rate limit and daily budget still apply per user.
- **Alternatives:** print the passwords (the guide's version: they leak into every screenshot and copy of the page).

## D037: Web toolchain versions (2026-10-30, Phase 6)

- **Decision:** React 19.3, Vite 8.3, Tailwind 4.3 (`@tailwindcss/vite`), Recharts 3.10, React Router 8.5, Vitest 5.0 + Testing Library + jsdom, Playwright 1.64, ESLint 10 + typescript-eslint 8.72, Prettier 3.9. **TypeScript is pinned to 6.0.x (`~6.0.3`), not 7.0**: typescript-eslint 8.72 supports TypeScript below 6.1 only (its peer range), checked with `npm view` on 2026-10-30.
- **Also:** fonts are self-hosted from `@fontsource` (Latin subsets only: Indonesian needs no other), so the app makes no request to Google Fonts; Recharts loads only when a bar or line chart is shown (its own 107 kB gzipped chunk); the main bundle is 93 kB gzipped.

## D038: The web app follows the API's choices (2026-10-30, Phase 6)

- **Decision:**
  - the chart type comes from the API (`chart`: kpi, bar, line, or table), which already checks it against the result's shape (D029). The app only draws it, with no entry animation: a half-drawn bar shows a wrong value (a screenshot caught one at 55%), and it respects reduced motion;
  - the table shows raw values with thousands separators (ids and years unchanged); the answer text keeps the agent's locale formatting; CSV keeps raw values, and cells starting with `=`, `+`, `-`, or `@` get a leading `'` so spreadsheets don't run them as formulas (result rows can contain untrusted text);
  - the stream is read with `fetch` and a small SSE parser (EventSource can't POST); the dev server proxies `/api`, so the app and the API share an origin and the cookie works without CORS. Steps arrive one by one through the proxy (checked: the first step at 128 ms, the next at 1,654 ms while the embedding model loaded);
  - dark theme only, with the colours and fonts of Baron's portfolio site.

## D039: A third EX score that accepts renamed labels (2026-10-30, before Phase 7)

- **Context:** in the Phase 4 live run, dev d019 and d027 failed for both systems although every number matched. The gold labelled rows `False`/`True` and `app`/`store`; the models wrote `weekday`/`weekend` and `Mobile app`/`Physical store`. EX matches columns by their exact values, so a renamed label column fails the case. Baron: a different label is acceptable as long as the meaning is the same.
- **Decision:** add `ex_relabeled` next to `ex_strict` and `ex_lenient` (both unchanged). It is lenient EX, plus: a gold label column (anything not numeric) may be matched by a predicted column that renames it one-to-one. Every gold measure column must still match exactly; rows are paired by those measures; each label must map to exactly one predicted value and back; a result with no measure column gets no relaxation.
- **Blind spot, handled by hand:** a code can't judge meaning, and a consistent swap (weekday counts labelled "weekend") also passes. Every report lists the cases that pass only under this rule ("Passing only with renamed labels (check by hand)"), so a person confirms the labels mean the same before the number is quoted.
- **Effect on the committed Phase 4 runs, re-scored offline (no API calls):** d019 and d027 pass for both agent and baseline; nothing else changes. The committed result files keep their original scores.
- **Alternatives:** an LLM judge for label meaning (paid, not deterministic); relabelling the gold to the models' wording (fits the gold to one model).

## D040: Periods with no data are refused, with follow-up suggestions (2026-10-30, before Phase 7)

- **Context:** dev d029 ("Bagaimana penjualan bulan ini?", asked on 2026-10-01) expected an answer for September 2026 with a stated assumption. Both live systems refused because October 2026 has no data. Baron preferred the refusal, with follow-up questions the user can pick.
- **Decision:**
  - a question about a period with no data at all (before 2024-01-01, after 2026-09-30, or the current month when the data stops earlier) is refused as unanswerable, with the reason (the dates the data covers) and up to three suggested questions the data can answer;
  - a question about a period or group that exists but has no matching rows is answered: zero or an empty table is the answer (for example a manager asking about another region's stores);
  - ambiguous but answerable questions still get a sensible default and a stated assumption ("this year" = 2026 so far);
  - suggestions are model text shown as clickable questions. They come only with "unanswerable" refusals (never with unsafe ones), at most three, and are kept only if the input guard accepts them and every year they name is inside the data window. No query ran, so they can't quote a result. They are not scored;
  - the SQL prompt, the agent state, `AgentResult`, `/api/ask`, the stream's `answer` event, the CLI, and the web app carry them; keyless demo question demo09 shows one.
- **Gold labels:** the rule was applied to both splits by reading only the questions about periods (dev + test, regex scan). One label changed: **dev d029** `state_assumption` → `refuse_unanswerable`. Test cases checked and unchanged: t001 (stores open today: current attributes, answerable), t043 ("this year": 2026 has data, assumption), t046 and t049 (already refusals), t051 (unsafe). No test-split question was used for prompts or examples.
- **Also found:** the input guard missed "Show the email of every customer" (it only matched "email address"). It now also catches names, emails, phones, and addresses "of" customers, employees, staff, or users; dev, example, and demo questions still pass.

## D041: `prompt_cache_key` kept, but it is a null result; the agent's extra cost is structural (2026-11-01, Phase 7)

- **Context:** in Phase 4 the agent cost about twice the baseline per question. The OpenAI adapter started sending `prompt_cache_key` (a hash of the system prompt) in `e442aaa`, in case calls were landing on different cache machines.
- **Finding:** on the dev split (40 questions, 1 repeat) cache reads went from 64,820 to 71,120 tokens and the cost from $0.0241 to $0.0244. No measurable change. The agent's SQL prompt is a 2,032-token static prefix followed by retrieved context that is different for every question. The retrieved part can't be read from the cache until the same question has been seen once. On the test split the agent costs about 2.2× the baseline on its first run of a question, and about 1.35× on repeats (docs/EVAL_RESULTS.md, finding 4).
- **Decision:** keep the key. It is correct, harmless, and contains no user data. Report the null result. Don't restructure the prompt only for caching at this price: the agent costs under $0.001 per question.
- **Alternatives:** move the retrieved context out of the system prompt (helps repeats only, not new questions); drop retrieval (no-retrieval caches better and was not less accurate here, but it doesn't scale to a bigger schema; D044).

## D042: Phase 7 ran two OpenAI models, not the guide's two or three across providers (2026-11-01, Phase 7)

- **Context:** BUILD_GUIDE §13 asks for a 2–3-model comparison. Baron chose a lower budget, with `gpt-6-luna` as the main model and `gpt-4o-mini` only if worth it. Approved: about $1.02 expected, a $2 hard cap, and a stop if any run cost more than twice its estimate.
- **Decision:** the test split × 3 repeats, run once, for: the agent and baseline, three ablations, and the critic on `gpt-6-luna`, plus the agent on `gpt-4o-mini`. No Anthropic models were run on the test split. Every run's cost stayed under its estimate. The total was $0.6669 (seven test runs $0.6424, plus the dev check $0.0244).
- **Why:** `gpt-4o-mini` is the model the flagship project uses, so it is the natural comparison. The Anthropic adapter is tested keylessly. A Claude comparison can be added later with its own budget approval.

## D043: The live model is `gpt-6-luna` (2026-11-02, Phase 7; confirmed by Baron)

- **Evidence** (test split, 60 questions × 3 repeats; docs/EVAL_RESULTS.md, finding 5):
  - EX relabeled: `gpt-6-luna` 0.933 ± 0.023, `gpt-4o-mini` 0.733 ± 0.046;
  - assumption stated on ambiguous questions: 0.933 vs 0.133;
  - false refusals: 0.013 vs 0.060;
  - cost per question: $0.000476 vs $0.000757;
  - p50 latency: 7.3 s vs 3.3 s.
- **Recommendation:** `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-6-luna` for live mode and the Phase 8 demo. It is more accurate and cheaper; the only cost is about 4 s more median latency, which the streamed step timeline makes visible rather than idle.
- **Status:** per BUILD_GUIDE §8.4 the choice is Baron's; he confirmed it on 2026-11-02. The `LLM_MODEL` default in `.env.example` and `config.py` changed from `claude-haiku-5-5` to `gpt-6-luna`. `LLM_PROVIDER` stays `fake`, so tests, CI, and the local demo stay keyless; live mode needs `LLM_PROVIDER=openai` and `LIVE_MODE_ENABLED=true`.

## D044: No tuning after the test run; the critic stays off (2026-11-02, Phase 7)

- **Context:** BUILD_GUIDE §13 says to analyse failures, fix using dev only, then re-measure on test. The agent scores 1.0 EX relabeled on all 40 dev questions (2026-11-01 dev run). The test failures are three questions:
  - t018: grouped by `region_id` instead of joining to the city;
  - t028: a fiscal-year mistake in one repeat, and in two repeats correct figures in a pivoted shape that EX can't match;
  - t010: one over-refusal of a partly covered year.
- **Decision:**
  - make no prompt or code change in response to test failures. Dev gives no failure to fix from, and fixing test cases directly would tune the system to the test set. They are documented in EVAL_RESULTS instead;
  - the t028 shape mismatch is not re-scored: changing the scorer after seeing a test failure would also bend the reported number;
  - the critic stays off by default (D028). On test it lowered EX relabeled from 0.933 to 0.873, raised false refusals from 0.013 to 0.067, and added 36% to the cost;
  - retrieval, repair, and few-shot stay on although their ablations were null on this schema. They are cheap, and they are what a larger schema would need. The docs say they were not measured to help here.
- **Follow-ups worth doing on dev first:** add dev cases for "city" questions and partly covered periods, so a future fix has dev evidence; consider an EX variant that accepts a pivoted result (wide vs long) as a scorer improvement, decided before the next test run.

## D045: Playwright stops its web servers with SIGTERM; CI jobs have timeouts (2026-11-02)

- **Context:** the first CI run on GitHub hung in the smoke test. On Linux, poethepoet starts its task in a new session (`start_new_session=True`), so Playwright's default teardown, SIGKILL to the process group of `uv run poe api`, never reaches uvicorn. The orphan holds the output pipe open and Playwright waits forever. Windows was not affected, and local runs reused already-running servers.
- **Decision:** `gracefulShutdown: { signal: "SIGTERM" }` for both web servers in `web/playwright.config.ts`. poe catches SIGTERM and stops its child. Also a Playwright `globalTimeout` of 10 minutes, and `timeout-minutes` on both CI jobs and the smoke step.
- **Why:** it keeps `poe api` as the one way to start the API. Verified in the Linux Playwright image: before, the test passed and the run hung; after, it passed and exited in 7 s.
- **Alternatives:** call `uv run uvicorn …` directly in the Playwright config (works, but duplicates the poe task's command); a CI-only kill step after the test (treats the symptom).
