"""Keyless mode: a rule-based stand-in for the model, so the agent runs with no API key.

For the demo questions in data/demo.yaml it replays a hand-written SQL query and answer
template; every other step (retrieval, validation, the read-only executor, row-level
security, number rendering) runs for real. Other questions are declined, or (for eval
plumbing runs) answered with one canned query. Keyless output is labelled as such and is
never a quality measure.
"""

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from sql_analyst.agent.schemas import AnswerDraft, ChartSpec, CriticVerdict, GuardVerdict, SQLDraft
from sql_analyst.dictionary.loader import REPO_ROOT
from sql_analyst.llm.base import Message

DEMO_PATH = REPO_ROOT / "data" / "demo.yaml"
GENERIC_SQL = "SELECT count(*) AS orders FROM analytics.fact_orders AS o"
_QUESTION = re.compile(r"^Question: (.*)$", re.MULTILINE)


class DemoQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    question: str
    lang: Literal["en", "id"]
    users: list[Literal["analyst", "manager_jakarta"]]
    expected: Literal["answer", "refuse_unsafe", "refuse_unanswerable"]
    assumptions: list[str] = Field(default_factory=list)
    sql: str | None = None
    template: str | None = None
    chart: ChartSpec | None = None
    reason: str | None = None  # scripted refusals only
    suggestions: list[str] = Field(default_factory=list)


def load_demo(path: Path = DEMO_PATH) -> list[DemoQuestion]:
    with path.open(encoding="utf-8") as f:
        return [DemoQuestion.model_validate(d) for d in yaml.safe_load(f)]


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


class KeylessResponder:
    """A `FakeLLM` responder. fallback='decline' (CLI) or 'generic' (eval plumbing runs)."""

    def __init__(
        self,
        demos: list[DemoQuestion] | None = None,
        fallback: Literal["decline", "generic"] = "decline",
    ):
        self.demos = {_norm(d.question): d for d in (demos if demos is not None else load_demo())}
        self.fallback = fallback

    def _demo(self, messages: list[Message]) -> DemoQuestion | None:
        m = _QUESTION.search(messages[-1].content)
        return self.demos.get(_norm(m.group(1))) if m else None

    def __call__(self, system: str, messages: list[Message], schema: type[BaseModel]) -> BaseModel:
        demo = self._demo(messages)
        if schema is SQLDraft:
            if demo and demo.sql:
                return SQLDraft(
                    decision="answer", sql=demo.sql, assumptions=demo.assumptions, confidence="high"
                )
            if demo and demo.expected == "refuse_unanswerable":
                return SQLDraft(
                    decision="refuse_unanswerable", reason=demo.reason, suggestions=demo.suggestions
                )
            if self.fallback == "generic":
                return SQLDraft(
                    decision="answer",
                    sql=GENERIC_SQL,
                    assumptions=["keyless mode: a canned query, not an answer to the question"],
                    confidence="low",
                )
            return SQLDraft(
                decision="refuse_unanswerable",
                reason="Keyless mode only answers the demo questions (data/demo.yaml). "
                "Live mode needs an API key and your OK to spend it.",
            )
        if schema is AnswerDraft:
            if demo and demo.template:
                return AnswerDraft(
                    template=" ".join(demo.template.split()),
                    chart=demo.chart or ChartSpec(type="table"),
                )
            return AnswerDraft(
                template="(keyless) The query returned {{row_count}} row(s).",
                chart=ChartSpec(type="table"),
            )
        if schema is CriticVerdict:
            return CriticVerdict(ok=True)
        if schema is GuardVerdict:
            return GuardVerdict(category="answerable")
        raise ValueError(f"keyless responder has no rule for {schema.__name__}")
