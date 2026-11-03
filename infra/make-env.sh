#!/usr/bin/env sh
# Write the production env file with fresh random secrets (docs/DEPLOYMENT.md).
#   infra/make-env.sh arunika-sql.duckdns.org   # public demo: HTTPS; live mode set up but off
#   infra/make-env.sh :80 --keyless             # local or CI: plain HTTP, no model calls
# Never overwrites an existing file and prints no secret. The OpenAI key is added by hand.
set -eu
SITE=${1:?usage: infra/make-env.sh SITE_ADDRESS [--keyless]}
ROOT=$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd))
OUT=${ENV_FILE:-$ROOT/.env}
if [ -e "$OUT" ]; then
    echo "$OUT already exists; not overwriting it." >&2
    exit 1
fi

case "$SITE" in
    :*) COOKIE_SECURE=false ;;  # plain HTTP (local, CI)
    *) COOKIE_SECURE=true ;;
esac
if [ "${2:-}" = "--keyless" ]; then PROVIDER=fake; else PROVIDER=openai; fi
rand() { openssl rand -hex "$1"; }

umask 077
cat >"$OUT" <<EOF
# Production env file written by infra/make-env.sh on $(date -u +%Y-%m-%d). Keep it private.
SITE_ADDRESS=$SITE

POSTGRES_DB=arunika
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$(rand 24)
NLQ_READER_PASSWORD=$(rand 24)
APP_WRITER_PASSWORD=$(rand 24)
RLS_SIGNING_KEY=$(rand 32)
JWT_SECRET=$(rand 32)
# Visitors use the one-click demo sign-in (D036); nobody needs these passwords.
DEMO_ANALYST_PASSWORD=$(rand 16)
DEMO_MANAGER_PASSWORD=$(rand 16)

LLM_PROVIDER=$PROVIDER
LLM_MODEL=gpt-6-luna
OPENAI_API_KEY=

COOKIE_SECURE=$COOKIE_SECURE
DEMO_LOGIN_ENABLED=true
RATE_LIMIT_PER_MINUTE=5
DAILY_BUDGET_USD=0.50
# Kill switch: stays false until the OpenAI key is in and the stack checks out.
LIVE_MODE_ENABLED=false
EOF
echo "Wrote $OUT (readable by its owner only; LLM_PROVIDER=$PROVIDER, COOKIE_SECURE=$COOKIE_SECURE)."
