"""The FastAPI app (BUILD_GUIDE §10): `uv run poe api`, docs at /api/docs.

    create_app()               # builds the executor, the agent, and the run store at startup
    create_app(resources=...)  # tests pass prebuilt resources

The agent is keyless unless LLM_PROVIDER names a paid provider; even then, paid calls only
happen with LIVE_MODE_ENABLED=true (otherwise /api/ask returns 503).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sql_analyst.agent.budget import BudgetLimits
from sql_analyst.agent.deps import AgentConfig
from sql_analyst.agent.factory import build_agent
from sql_analyst.api.deps import Resources
from sql_analyst.api.logs import RequestLogMiddleware, configure_logging
from sql_analyst.api.routes import ask, auth, ops, reference, runs
from sql_analyst.api.store import AppStore
from sql_analyst.config import Settings, get_settings
from sql_analyst.dictionary.loader import load_dictionary
from sql_analyst.safety.executor import Executor

DESCRIPTION = """Ask questions about PT Arunika Niaga, a **fictional** retailer with **synthetic**
data, in English or Bahasa Indonesia. Every answer comes with the SQL that produced it, the
rows, and numbers filled in by code from those rows. Sign in with `POST /api/auth/login`;
the session is an httpOnly cookie. This is a portfolio project built to production standards."""


def build_resources(settings: Settings) -> Resources:
    settings.jwt_key()  # fail fast on a missing secret
    executor = Executor.from_settings(settings, load_dictionary())
    store = AppStore(settings.writer_conninfo())
    try:
        provider = settings.llm_provider
        agent = build_agent(
            settings,
            executor,
            provider=provider,
            model=None if provider == "fake" else settings.llm_model,
            config=AgentConfig(limits=BudgetLimits.from_settings(settings)),
            run_store=store,
        )
    except Exception:
        store.close()
        executor.close()
        raise
    return Resources(settings=settings, agent=agent, store=store, executor=executor)


def create_app(settings: Settings | None = None, resources: Resources | None = None) -> FastAPI:
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned = resources is None
        app.state.resources = resources or build_resources(settings or get_settings())
        try:
            yield
        finally:
            if owned:
                app.state.resources.close()

    app = FastAPI(
        title="Agentic SQL Analyst API",
        version="0.5.0",
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(RequestLogMiddleware)
    for module in (auth, ask, runs, reference, ops):
        app.include_router(module.router)
    return app
