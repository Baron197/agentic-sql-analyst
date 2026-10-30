"""What the nodes need besides the state: the model, the executor, retrieval, and config."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

from pydantic import BaseModel, Field

from sql_analyst.agent import prompts
from sql_analyst.agent.budget import BudgetLimits
from sql_analyst.dictionary.models import Dictionary
from sql_analyst.dictionary.render import render_dictionary, render_static
from sql_analyst.llm.base import LLMClient, LLMError, Message, T
from sql_analyst.observability import LLMCall, RunSink
from sql_analyst.retrieval.search import Retriever
from sql_analyst.safety.executor import QueryResult
from sql_analyst.safety.scope import UserScope
from sql_analyst.safety.validator import SQLValidator, ValidatedSQL


class AgentConfig(BaseModel):
    """Switches for the ablations (BUILD_GUIDE §9) plus run limits."""

    retrieval: bool = True  # False: the whole dictionary goes into the prompt, no value matching
    repair: bool = True  # False: the first failed attempt ends the run
    critic: bool = False  # optional LLM check of the result (measured, not assumed to help)
    few_shot: bool = True  # False: no retrieved examples in the prompt
    guard_llm: bool = False  # optional LLM classification of the question
    limits: BudgetLimits = Field(default_factory=BudgetLimits)
    as_of: date | None = None  # "today" for relative dates; default: the day after the data ends
    answer_rows: int = 30  # result rows shown to the model when it writes the answer
    max_result_checks: int = 1  # times check_result may send the run back

    def variant(self) -> str:
        """'agent', or e.g. 'agent-no-retrieval+critic' for an ablation."""
        parts = [
            name
            for name, on in [
                ("no-retrieval", not self.retrieval),
                ("no-repair", not self.repair),
                ("no-few-shot", not self.few_shot),
                ("critic", self.critic),
                ("guard-llm", self.guard_llm),
            ]
            if on
        ]
        return "agent" + ("-" + "+".join(parts) if parts else "")


class QueryRunner(Protocol):
    """The part of safety.executor.Executor the agent uses (tests pass a stub)."""

    def run_validated(self, validated: ValidatedSQL, scope: UserScope) -> QueryResult: ...


@dataclass
class AgentDeps:
    llm: LLMClient
    executor: QueryRunner
    validator: SQLValidator
    dictionary: Dictionary
    retriever: Retriever | None
    config: AgentConfig = field(default_factory=AgentConfig)
    run_store: RunSink | None = None

    def __post_init__(self) -> None:
        if self.config.retrieval and self.retriever is None:
            raise ValueError("retrieval is on but no retriever was given")
        if self.config.as_of is None:
            self.config = self.config.model_copy(
                update={"as_of": self.dictionary.data_window.end + timedelta(days=1)}
            )
        schema_text = (
            render_static(self.dictionary)
            if self.config.retrieval
            else render_dictionary(self.dictionary)
        )
        # Identical for every question, so providers can cache it.
        self.sql_system = prompts.load("sql_system") + "\n" + schema_text

    @property
    def llm_nodes(self) -> set[str]:
        nodes = {"generate_sql", "write_answer"}
        if self.config.guard_llm:
            nodes.add("guard_input")
        if self.config.critic:
            nodes.add("check_result")
        return nodes


def call_llm(
    deps: AgentDeps, node: str, system: str, user: str, schema: type[T], max_tokens: int
) -> tuple[T | None, list[LLMCall], str | None]:
    """One model call: (parsed or None, the call's usage records, error message or None)."""
    try:
        parsed, usage = deps.llm.generate_structured(
            system, [Message(role="user", content=user)], schema, max_tokens=max_tokens
        )
    except LLMError as e:
        return None, ([LLMCall(node=node, usage=e.usage)] if e.usage else []), str(e)
    return parsed, [LLMCall(node=node, usage=usage)], None
