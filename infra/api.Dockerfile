# The API image (Phase 8): FastAPI + the agent, also used by the one-off `seed` service.
# Build from the repo root: docker build -f infra/api.Dockerfile .
ARG PYTHON_IMAGE=python:3.12.16-slim-bookworm

FROM ghcr.io/astral-sh/uv:0.13.3 AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Dependencies first, so a code change doesn't reinstall them.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-dev --no-install-project
# The package is installed editable on purpose: it finds data/*.yaml relative to the repo layout.
COPY backend/src backend/src
COPY data data
RUN uv sync --locked --no-dev
# Bake the embedding model into the image, so neither startup nor seeding downloads it.
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RUN HF_HUB_DISABLE_TELEMETRY=1 /app/.venv/bin/python -c \
    "from fastembed import TextEmbedding; TextEmbedding(model_name='${EMBEDDING_MODEL}', cache_dir='/app/.cache/fastembed')" \
    && chmod -R a+rX /app/.cache

FROM ${PYTHON_IMAGE}
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
# Owned by root and read-only for the app user: the container can't change its own code.
COPY --from=build /app /app
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    ORT_DISABLE_TELEMETRY=1 \
    EMBEDDING_CACHE_DIR=/app/.cache/fastembed
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=3 CMD \
    python -c "import json, sys, urllib.request as u; sys.exit(json.load(u.urlopen('http://127.0.0.1:8000/api/health', timeout=4))['status'] != 'ok')"
# One worker: the rate limits are counted in memory (D032). Forwarded headers are trusted from
# any address because only the Caddy container can reach this port (internal network).
CMD ["uvicorn", "sql_analyst.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
