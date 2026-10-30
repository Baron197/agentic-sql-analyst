"""Helpers for agent tests: a scripted model, a stub executor, an in-memory retriever.

None of these need a database, an API key, or a model download.
"""

from typing import Any

import pytest

from sql_analyst.agent.budget import BudgetLimits
from sql_analyst.agent.deps import AgentConfig, AgentDeps
from sql_analyst.agent.graph import Agent
from sql_analyst.dictionary.loader import load_dictionary
from sql_analyst.dictionary.values import ColumnValue
from sql_analyst.llm.fake import FakeLLM
from sql_analyst.observability import RunStore
from sql_analyst.retrieval.embed import HashEmbedder
from sql_analyst.retrieval.examples import load_examples
from sql_analyst.retrieval.search import Retriever
from sql_analyst.safety.executor import QueryResult
from sql_analyst.safety.validator import SQLValidator, ValidatedSQL
from sql_analyst.users import DEMO_USERS

DICTIONARY = load_dictionary()
VALIDATOR = SQLValidator(DICTIONARY)
ANALYST = DEMO_USERS["analyst"]
MANAGER = DEMO_USERS["manager_jakarta"]

ORDERS_SQL = "SELECT count(*) AS orders FROM analytics.fact_orders AS o"
BY_CHANNEL_SQL = (
    "SELECT c.channel_name, count(*) AS orders FROM analytics.fact_orders AS o "
    "JOIN analytics.dim_channel AS c ON c.channel_id = o.channel_id GROUP BY c.channel_name"
)
VALUES = [
    ColumnValue(view="dim_region", column="city", value="Jakarta", row_count=1),
    ColumnValue(view="dim_region", column="city", value="Surabaya", row_count=1),
    ColumnValue(view="dim_region", column="city_code", value="JKT", row_count=1),
    ColumnValue(view="dim_region", column="region_group", value="Jabodetabek", row_count=5),
    ColumnValue(view="fact_orders", column="region_code", value="JKT", row_count=900),
    ColumnValue(view="dim_category", column="category_name_id", value="Elektronik", row_count=1),
    ColumnValue(view="dim_category", column="category_name_id", value="Ibu & Anak", row_count=1),
    ColumnValue(view="dim_channel", column="channel_code", value="store", row_count=1),
    ColumnValue(view="dim_channel", column="channel_code", value="website", row_count=1),
    ColumnValue(
        view="dim_store", column="store_name", value="Arunika Tangerang Gading Serpong", row_count=1
    ),
    ColumnValue(view="fact_payments", column="payment_method", value="ewallet", row_count=50),
]
RETRIEVER = Retriever.in_memory(DICTIONARY, load_examples(), VALUES, HashEmbedder())


class ScriptedLLM(FakeLLM):
    """Answers each schema with the next queued response (an object or an exception)."""

    def __init__(self, script: dict[type, list[Any]] | None = None):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.calls: list[tuple[str, str, str]] = []  # (schema, system, last user message)
        super().__init__(self._respond)

    def _respond(self, system, messages, schema):
        self.calls.append((schema.__name__, system, messages[-1].content))
        queue = self.script.get(schema)
        if not queue:
            raise AssertionError(f"unexpected {schema.__name__} call")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def messages(self, schema_name: str) -> list[str]:
        return [m for s, _sys, m in self.calls if s == schema_name]


class StubExecutor:
    """Returns queued outcomes: (columns, rows[, truncated]) tuples or SafetyError instances."""

    def __init__(self, *outcomes: Any):
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, Any]] = []

    def run_validated(self, validated: ValidatedSQL, scope) -> QueryResult:
        self.calls.append((validated.sql, scope))
        if not self.outcomes:
            raise AssertionError("unexpected query")
        item = self.outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        columns, rows, *rest = item
        truncated = bool(rest and rest[0])
        return QueryResult(
            sql=validated.sql,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            plan_cost=10.0,
            elapsed_ms=1.0,
        )


def make_deps(
    llm: FakeLLM,
    executor: StubExecutor | None = None,
    *,
    run_store: RunStore | None = None,
    limits: dict[str, Any] | None = None,
    **config: Any,
) -> AgentDeps:
    cfg = AgentConfig(limits=BudgetLimits(**(limits or {})), **config)
    return AgentDeps(
        llm=llm,
        executor=executor or StubExecutor(),
        validator=VALIDATOR,
        dictionary=DICTIONARY,
        retriever=RETRIEVER if cfg.retrieval else None,
        config=cfg,
        run_store=run_store,
    )


def make_agent(llm: FakeLLM, executor: StubExecutor | None = None, **kwargs: Any) -> Agent:
    return Agent(make_deps(llm, executor, **kwargs))


@pytest.fixture
def run_store(tmp_path) -> RunStore:
    return RunStore(tmp_path / "runs")
