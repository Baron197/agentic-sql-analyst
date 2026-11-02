#!/usr/bin/env sh
# docker compose for the production stack, with the env file passed in (docs/DEPLOYMENT.md).
# ENV_FILE defaults to .env at the repo root; local and CI runs point it at a throwaway file.
#   infra/compose.sh build | up -d | ps | logs -f api | down
set -eu
ROOT=$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd))
ENV_FILE=${ENV_FILE:-$ROOT/.env}
export ENV_FILE
if [ ! -f "$ENV_FILE" ]; then
    echo "No env file at $ENV_FILE: run infra/make-env.sh first." >&2
    exit 1
fi
exec docker compose -f "$ROOT/infra/docker-compose.prod.yml" --env-file "$ENV_FILE" "$@"
