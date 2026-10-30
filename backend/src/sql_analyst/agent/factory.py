"""Build an `Agent` from settings: the model (keyless by default), retrieval, the run store."""

from typing import Literal

from sql_analyst.agent.deps import AgentConfig, AgentDeps
from sql_analyst.agent.graph import Agent
from sql_analyst.agent.keyless import KeylessResponder
from sql_analyst.config import Settings
from sql_analyst.dictionary.loader import load_dictionary
from sql_analyst.llm.factory import make_llm
from sql_analyst.observability import RunSink, RunStore
from sql_analyst.retrieval.embed import Embedder, make_embedder
from sql_analyst.retrieval.search import Retriever
from sql_analyst.safety.executor import Executor


def build_agent(
    settings: Settings,
    executor: Executor,
    *,
    provider: str = "fake",
    model: str | None = None,
    config: AgentConfig | None = None,
    keyless_fallback: Literal["decline", "generic"] = "decline",
    store_runs: bool = True,
    embedder: Embedder | None = None,
    run_store: RunSink | None = None,
) -> Agent:
    """provider='fake' is keyless; 'openai' or 'anthropic' are live (paid; need a key)."""
    config = config or AgentConfig(limits=AgentConfig().limits.from_settings(settings))
    dictionary = load_dictionary()
    llm = make_llm(
        provider, model, settings, fake_responder=KeylessResponder(fallback=keyless_fallback)
    )
    retriever = (
        Retriever.from_db(executor.pool, dictionary, embedder or make_embedder(settings))
        if config.retrieval
        else None
    )
    deps = AgentDeps(
        llm=llm,
        executor=executor,
        validator=executor.validator,
        dictionary=dictionary,
        retriever=retriever,
        config=config,
        run_store=run_store or (RunStore(settings.runs_dir) if store_runs else None),
    )
    return Agent(deps)
