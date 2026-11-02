# Deployment

How the public demo runs on one AWS EC2 instance with Docker Compose, and how to set it up, operate it, and take it down. PT Arunika Niaga and all its data are fictional and synthetic; this is a portfolio project built to production standards.

## What runs

```
Internet ──443/80──► web: Caddy (the built React app + HTTPS)
                       ├─ /        → static files
                       └─ /api/*   → api:8000  FastAPI + the agent (1 worker)
                                         └─► db:5432  Postgres 16 + pgvector
```

| Service | Image | Notes |
|---|---|---|
| `web` | `infra/web.Dockerfile`: the Vite build inside `caddy:2.11.7-alpine` | The only service with published ports. Gets and renews a Let's Encrypt certificate, redirects HTTP to HTTPS, and sets the security headers. Streams `/api` responses unbuffered. |
| `api` | `infra/api.Dockerfile`: Python 3.12 slim, locked dependencies, embedding model baked in | Logs in as `nlq_reader` (read-only) and `app_writer` (run store) only. It never gets the database owner password. |
| `db` | `pgvector/pgvector:pg16` | Not published to the host. Data in the `pgdata` volume. |
| `seed` | the API image, run on demand | Builds the schemas, loads the deterministic seed, builds the retrieval index, and sets up the API schema and demo users (about 25 s). |

- **Same origin.** The app and the API share one address, so the session cookie needs no CORS. Live answers stream through Caddy step by step (server-sent events).
- **Hardening.** `api` and `web` run as non-root users on read-only filesystems with every Linux capability dropped (Caddy keeps only `NET_BIND_SERVICE`, for ports 80 and 443) and `no-new-privileges`. Each container has a memory limit and capped log files.
- **Secrets.** Only in `.env` on the server, created by `infra/make-env.sh` with random values and owner-only permissions. Never in git or in an image (`.dockerignore` is an allow-list).

The same stack runs in CI on every push, keyless (the `docker` job): build, seed, start, and [`infra/smoke_public.py`](../infra/smoke_public.py) through Caddy.

## Monthly cost

Prices checked on 2026-11-02 for Asia Pacific (Singapore) `ap-southeast-1`, Linux, on demand, 730 hours a month. Jakarta (`ap-southeast-3`) lists the same instance price.

| Item | Price | Per month |
|---|---|---|
| EC2 `t4g.small` (2 vCPU Arm, 2 GB) | $0.0212 / hour | $15.48 |
| EBS gp3, 20 GB | $0.096 / GB-month | $1.92 |
| Public IPv4 address (the Elastic IP, while attached) | $0.005 / hour | $3.65 |
| **Infrastructure** | | **≈ $21** |
| OpenAI `gpt-6-luna` | capped at `DAILY_BUDGET_USD` = $1.00 a day | **$0 to $31** |

- **The model cost is capped, and the expected cost is far lower.** On the Phase 7 test split the agent cost $0.000476 per question on average, and $0.000659 per new question with a cold cache ([EVAL_RESULTS.md](EVAL_RESULTS.md)). The $1 daily cap allows about 1,500 new questions a day.
- **Data transfer** for a demo page and JSON answers stays within the free monthly allowance.
- **AWS Free plan.** On a new account's Free plan, the infrastructure is paid from the sign-up credits ($100, plus up to $100 more from AWS's onboarding activities), which last about 5 to 9 months at this rate. The Free plan itself ends after 6 months: the account is then suspended unless it is upgraded to a paid plan, and the demo goes offline.
- Sources: [t4g.small prices by region](https://aws-pricing.com/t4g.small.html) (updated 2026-10-31), [ap-southeast-1 prices incl. EBS gp3](https://aws-pricing.com/ap-southeast-1.html), [AWS public IPv4 charge](https://aws.amazon.com/blogs/aws/new-aws-public-ipv4-address-charge-public-ip-insights). Check the [AWS Pricing Calculator](https://calculator.aws/) before relying on them.

## One-time setup

You need an AWS account, an SSH client, and a free [DuckDNS](https://www.duckdns.org/) account (or a domain of your own).

### 1. Launch the instance (AWS console)

EC2 → Instances → **Launch instances**:
- **Region:** Asia Pacific (Singapore) or (Jakarta).
- **AMI:** Ubuntu Server 24.04 LTS, architecture **64-bit (Arm)**.
- **Instance type:** `t4g.small`. (`t3.small` with the x86 AMI also works; the images build on either.)
- **Key pair:** create one (`.pem`) and keep it in `~/.ssh/`.
- **Network:** a new security group with three inbound rules:
  - SSH (22) from **My IP** only;
  - HTTP (80) from anywhere (Let's Encrypt checks the domain over port 80; Caddy then redirects to HTTPS);
  - HTTPS (443) from anywhere.
- **Storage:** 20 GiB gp3.

Then EC2 → **Elastic IPs** → Allocate → Associate it with the instance, so the address survives a stop and start.

### 2. Point a domain at it

At DuckDNS, add a subdomain (for example `arunika-sql`) and set its IP to the Elastic IP. `arunika-sql.duckdns.org` then resolves to the instance. Check with `nslookup arunika-sql.duckdns.org`.

### 3. Prepare the server

```bash
ssh -i ~/.ssh/YOUR-KEY.pem ubuntu@arunika-sql.duckdns.org

# 2 GB of swap: building the images on a 2 GB instance needs it.
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Docker Engine and Compose from Ubuntu's archive, security updates applied automatically.
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git unattended-upgrades
sudo usermod -aG docker ubuntu   # then log out and back in
docker compose version            # needs 2.24 or later
```

### 4. Get the code and write the secrets

```bash
git clone https://github.com/Baron197/agentic-sql-analyst.git
cd agentic-sql-analyst
infra/make-env.sh arunika-sql.duckdns.org
nano .env    # paste the OpenAI key after OPENAI_API_KEY= ; save
```

`make-env.sh` writes random passwords and keys, `COOKIE_SECURE=true`, one-click demo sign-in, `gpt-6-luna`, a $1.00 daily budget, and **`LIVE_MODE_ENABLED=false`**: nothing can spend money until you switch live mode on in step 6. It refuses to overwrite an existing `.env` and prints no secret. Visitors use the one-click demo sign-in, so nobody needs the demo passwords it generates.

A spending limit on the OpenAI project (OpenAI dashboard → project → limits) is a second safety net under the app's daily budget.

### 5. Build, seed, start

```bash
infra/compose.sh build                # about 10 minutes the first time on a t4g.small
infra/compose.sh run --rm seed        # about 25 s
infra/compose.sh up -d --wait
infra/compose.sh ps                   # db, api, web: all healthy
```

Caddy asks Let's Encrypt for a certificate on the first request; the DNS record and port 80 must be in place first.

### 6. Check it, then switch live mode on

```bash
python3 infra/smoke_public.py --url https://arunika-sql.duckdns.org --expect-status 503
```

With live mode off, every step passes and the question is refused with 503 `live_mode_disabled`: this is the kill switch working. Then set `LIVE_MODE_ENABLED=true` in `.env` and:

```bash
infra/compose.sh up -d --force-recreate api
python3 infra/smoke_public.py --url https://arunika-sql.duckdns.org --ask   # one paid question, about $0.0007
```

### 7. Check the daily budget cap

Set `DAILY_BUDGET_USD=0` in `.env` and recreate `api`. Today's spend is already at or above the cap, so the next question is refused before any model call, at no cost:

```bash
infra/compose.sh up -d --force-recreate api
python3 infra/smoke_public.py --url https://arunika-sql.duckdns.org --expect-status 429   # daily_budget_reached
```

Then set it back to `1.00` and recreate `api` again. Both refusal paths (503 and 429) were also rehearsed on the production stack locally with a placeholder key on 2026-11-02, with no model calls.

## Operations

All commands run in the repo folder on the server. `.env` changes take effect when the `api` container is recreated: `infra/compose.sh up -d --force-recreate api`.

| Task | How |
|---|---|
| Stop all model spending now (kill switch) | `LIVE_MODE_ENABLED=false` in `.env`, recreate `api`. Questions get 503; the rest of the site keeps working. |
| Change the daily budget | `DAILY_BUDGET_USD=…` in `.env`, recreate `api`. Spend is counted per day in WIB from stored runs, so it survives restarts. |
| See spend, error rate, latency | Sign in, then `GET /api/metrics` (or the History page). |
| Logs | `infra/compose.sh logs -f api` (JSON lines, no prompts or secrets) |
| Deploy a new version | `git pull && infra/compose.sh build && infra/compose.sh up -d --wait` |
| Reload the data | `infra/compose.sh run --rm seed` (keeps users and stored runs) |
| Restart after a reboot | Automatic (`restart: unless-stopped`) |

**Backups.** None are needed for the data: `seed` rebuilds it deterministically. Stored runs (`app.runs`) are demo history and are lost only if the `pgdata` volume is deleted.

**Shared demo account.** Every visitor who clicks "Try as analyst" uses the same `analyst@demo` user, so its limit of 10 questions a minute and the daily budget are shared by all visitors. That is the intended ceiling for a public demo.

## Taking it down

```bash
infra/compose.sh down -v      # stops everything and deletes the database and certificate volumes
```

Then in the AWS console: terminate the instance, **release the Elastic IP** (an unattached Elastic IP is still billed), and delete the DuckDNS record.

## Rehearse locally

The whole stack runs on Docker Desktop with a throwaway env file and no model calls:

```bash
export ENV_FILE="$PWD/.env.prodtest"
infra/make-env.sh :80 --keyless
printf 'HTTP_PORT=8088\nHTTPS_PORT=8443\n' >> "$ENV_FILE"
infra/compose.sh build && infra/compose.sh run --rm seed && infra/compose.sh up -d --wait
uv run poe smoke-public --url http://127.0.0.1:8088 --ask
infra/compose.sh down -v && rm "$ENV_FILE"
```

`.env.*` files are gitignored. The local project is named `sql-analyst`, so it doesn't touch the development database container.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| The build is killed or the instance freezes | No swap (step 3). |
| No certificate; the browser shows a TLS error | The domain doesn't point at the Elastic IP yet, or port 80 is closed. `infra/compose.sh logs web` shows Caddy's ACME attempts. |
| 502 from `/api` | The API is still starting (the embedding model loads in a few seconds) or unhealthy: `infra/compose.sh ps`, then `logs api`. |
| Every question returns 503 | Live mode is off (`LIVE_MODE_ENABLED=false`), as designed. |
| Questions return 429 | The per-user rate limit (`rate_limited`) or the daily budget (`daily_budget_reached`) was reached. |
| `health` says `degraded` | The API can't reach the database: check `db` with `infra/compose.sh ps`. |
