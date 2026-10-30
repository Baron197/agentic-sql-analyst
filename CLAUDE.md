# Agentic SQL Analyst: rules for Claude

Portfolio project by Baron Purwa Hartono (AI Engineer). An agentic natural-language-to-SQL analyst: a business user asks a question in English or Bahasa Indonesia about a fictional company's database and gets an answer they can verify: the SQL, the rows behind it, and numbers filled in by code, never typed by the model.

**The full spec is `BUILD_GUIDE.md`. The current state is `PROGRESS.md`. Read both at the start of every session.**

## How we work

- One phase at a time, in the order of BUILD_GUIDE.md §13. Don't start the next phase until Baron says so.
- Start each phase with a short plan (files, steps, risks, open questions) and wait for Baron's OK before writing code.
- A phase is done only when every item in its Definition of Done passes. Show the command output as proof.
- Run the check task (lint + tests) before every commit. Commit at the end of each phase, or at each stable point within one, with a short imperative message.
- At the end of every session, update `PROGRESS.md`: what was done, decisions made, open issues, and the exact next step. A fresh chat must be able to continue from it alone.
- Record each non-obvious design choice in `docs/DECISIONS.md` (context, decision, why, alternatives considered). Keep entries short.
- If the guide is wrong or a library has changed, say so, propose an alternative, and record it in DECISIONS.md. Don't silently diverge.
- Prefer simple, readable code over clever code: small modules, type hints, Pydantic models at boundaries, brief docstrings.

## Hard rules

- Never push, create a GitHub repository, or deploy without Baron's explicit OK in the current chat.
- Never ask Baron to paste API keys or passwords into the chat. Secrets live in `.env` (gitignored); `.env.example` lists the names only.
- Anything that calls a paid LLM API (live mode, evals) needs Baron's OK first, with an estimated cost. Default to keyless mode.
- Tests and CI must run with no API key.
- The database role the agent uses stays read-only. Never weaken a safety check, a test, or a threshold to make something pass.
- Never use eval test-split questions as few-shot examples or for prompt tuning.

## Honesty rules (README, docs, UI, commit messages)

- This is a portfolio project built to production standards. Never write that it is "in production", "used by customers" or "real users", or "at scale".
- The company and all data are fictional and synthetic. Say so in the README and in the UI.
- Every metric in the docs must come from a committed file in `eval/results/` and state the date, model, number of questions, and repeats. Report mean ± std when repeated.
- Keyless, fake, and replay runs test the plumbing, not quality. Never present their numbers as accuracy.
- Publish null or negative results (for example an ablation that didn't help) instead of hiding them.

## Environment

- Windows 11 (PowerShell and Git Bash). Docker Desktop runs Postgres. Python 3.12 managed with `uv`. Node LTS for the web app.
- `make` isn't available by default on Windows: use a cross-platform task runner (poethepoet tasks in `pyproject.toml`, run with `uv run poe <task>`).
- Commands (run from the repo root; `uv run poe` lists all tasks):
  - `uv sync`: install Python 3.12 deps into `.venv` (uses `uv.lock`).
  - `uv run poe check`: ruff lint + format check + CI workflow schema check + pytest. Run before every commit.
  - `uv run poe test`: pytest only. Tests marked `db` skip if Postgres is down, unless `REQUIRE_DB=1` (set in CI).
  - `uv run poe format`: apply ruff formatting.
  - `uv run poe db-up` / `db-down`: start (waits until healthy) / stop the Postgres container.
  - `uv run poe db-reset`: `db-up`, `db-load`, `index-build`, then `app-setup` (~25 s). The usual way to get a fresh database.
  - `uv run poe app-setup`: create the API's `app` schema and write-only `app_writer` role, and seed the demo users from `.env` (idempotent; keeps stored runs).
  - `uv run poe api`: run the API on http://127.0.0.1:8000 (docs at `/api/docs`). Keyless unless `LLM_PROVIDER` is a paid provider and `LIVE_MODE_ENABLED=true`.
  - `uv run poe index-build`: embed the dictionary, glossary, and few-shot examples into pgvector (schema `retrieval`) and store the categorical values. Run after `db-load`; the first run downloads the embedding model (~220 MB) into `.cache/fastembed`.
  - `uv run poe db-load`: drop and rebuild the `core` + `analytics` schemas and load the deterministic seed into whatever database `.env` points at (CI uses this).
  - `uv run poe db-checksum`: per-table fingerprint of the loaded data; identical on every rebuild.
  - `uv run poe db-wipe`: stop the container and delete its volume.
  - `uv run poe db-ping`: connect and check the server version and pgvector.
  - `uv run poe eval --system gold|baseline|agent --mode keyless|live --split dev|test|dev,test [--repeats N] [--limit N] [--model M] [--ablation no-retrieval,no-repair,no-few-shot] [--critic]`: eval harness; results in `eval/results/`. Live mode prints a cost estimate and needs `--confirm-live` and Baron's OK first.
  - `uv run poe ask "…" [--user analyst|manager_jakarta] [--mode keyless|live --model M] [--json]`: ask the agent. Keyless (default) answers the demo questions in `data/demo.yaml`; `uv run poe ask` with no question lists them. Live mode is a paid call. Runs are saved to `runs/` (gitignored).
  - `uv run poe web-install`: `npm ci` in `web/` (Node LTS; TypeScript pinned to 6.0, D037).
  - `uv run poe web`: the web app on http://127.0.0.1:5173 (proxies `/api` to `poe api`; run both).
  - `uv run poe web-check`: web lint, Prettier check, typecheck, Vitest, build. Run before every commit that touches `web/`.
  - `uv run poe web-e2e`: Playwright smoke test (starts `poe api` and the web server if needed; Postgres must be up). `uv run poe web-screenshots` writes `docs/screenshots/`.
  - One-time: `npx --prefix web playwright install chromium`.
- Never print the demo passwords, `JWT_SECRET`, or other `.env` values in the chat or in docs; read them into shell variables.
- Local `.env` is created from `.env.example`; Docker Desktop must be running for any `db-*` task.
- Use `127.0.0.1`, never `localhost`, for the database host on this machine: `localhost` resolves to IPv6 first and each connection hangs ~130 s (docs/DECISIONS.md D006).
- The `analytics` views are row-level secured (Phase 2): any connection, the admin included, sees zero rows until it applies a signed scope with `sql_analyst.safety.scope.apply_scope` in the same transaction. Query `core.*` directly as admin for raw data. The agent only ever uses `safety.executor.Executor` (role `nlq_reader`). See docs/SECURITY.md.

## When writing LLM code

- All model calls go through the provider-agnostic interface in `backend/src/sql_analyst/llm/`.
- For the Anthropic adapter, use the `claude-api` skill. Current Claude models reject `temperature`, assistant prefill, and forced `tool_choice`; use structured outputs.
- Record tokens, cost, and latency for every LLM call.

## Reference implementation

Baron's flagship project uses the same patterns (budget guard on every graph edge, per-run cost/latency tracing, human-approval interrupt, MCP server, CI evaluation gate):
`D:\Portfolios\Multi-AI-Agent Project\Multi AI Agents Project\agentic-research-assistant`
Read it for conventions when useful. Don't copy code blindly.
