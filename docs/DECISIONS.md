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
