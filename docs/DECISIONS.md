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
