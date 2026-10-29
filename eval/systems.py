"""What every evaluated system returns, plus the gold oracle used for sanity checks."""

import time
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from eval.cases import EvalCase
from sql_analyst.llm.base import Usage
from sql_analyst.safety.errors import SafetyError
from sql_analyst.safety.executor import Executor

Decision = Literal["answer", "refuse_unsafe", "refuse_unanswerable", "error"]


class Prediction(BaseModel):
    case_id: str
    decision: Decision
    sql: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    reason: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    truncated: bool = False
    executed: bool = False  # ran through the scoped, read-only executor
    answer: str | None = None
    usages: list[Usage] = Field(default_factory=list)
    latency_ms: float = 0.0

    @property
    def cost_usd(self) -> float:
        return round(sum(u.cost_usd for u in self.usages), 8)


class System(Protocol):
    name: str

    def run(self, case: EvalCase) -> Prediction: ...


def execute_into(pred: Prediction, executor: Executor, sql: str, case: EvalCase) -> None:
    """Run SQL as the case's user and store the result or the safety error on `pred`."""
    try:
        result = executor.run(sql, case.scope)
    except SafetyError as e:
        pred.error_code, pred.error_message = e.code, e.message
        return
    pred.sql = result.sql
    pred.columns, pred.rows, pred.truncated = result.columns, result.rows, result.truncated
    pred.executed = True


class GoldSystem:
    """Replays the gold SQL and the expected refusals: must score 100% (sanity check)."""

    name = "gold"

    def __init__(self, executor: Executor):
        self.executor = executor

    def run(self, case: EvalCase) -> Prediction:
        started = time.perf_counter()
        if case.gold_sql is None:
            pred = Prediction(case_id=case.id, decision=case.expected, reason="gold refusal")
        else:
            pred = Prediction(case_id=case.id, decision="answer")
            if case.expected == "state_assumption":
                pred.assumptions = [case.notes or "default interpretation"]
            execute_into(pred, self.executor, case.gold_sql, case)
        pred.latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return pred
