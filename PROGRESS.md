# Progress

Updated by Claude at the end of every session. A fresh chat continues from here.

## Status

| Phase | Status | Notes |
|---|---|---|
| 0 Scaffold | **done** (2026-10-29) | all DoD items pass; see session log |
| 1 Synthetic enterprise database | not started | next |
| 2 Safety layer | not started | |
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

- Docker Desktop 4.80 on this machine crashed at startup because of leftover AF_UNIX socket files that Windows refuses to delete (error 1920). Workaround used on 2026-10-29: quit Docker Desktop and rename the folders aside: `%LOCALAPPDATA%\Docker\run` and `%LOCALAPPDATA%\docker-secrets-engine` (now `*.stale-20261029*`). They can be deleted after a reboot. If Docker fails to start again with "The file cannot be accessed by the system", repeat that. Quitting Docker Desktop normally (not killing it) should avoid it.

## Next step

Phase 1: Synthetic enterprise database (BUILD_GUIDE §6 and §13). Start with a plan: `core` DDL, `analytics` views, deterministic seed (seed=42, Faker `id_ID`; look up real Ramadan/Lebaran dates for 2024–2026), `data/dictionary.yaml`, the planted injection row, `docs/DATA.md`, and extending `poe db-reset` to load schema + seed in under 2 minutes.

## Session log

_(newest first: date, what was done, decisions, issues)_

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
