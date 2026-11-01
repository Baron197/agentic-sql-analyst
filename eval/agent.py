"""The agent as an evaluated system: maps an AgentResult to the harness's Prediction."""

from eval.cases import AS_OF_DATE, EvalCase
from eval.systems import Prediction
from sql_analyst.agent.graph import Agent
from sql_analyst.agent.nodes.finalize import AgentResult

_REFUSAL_DECISION = {
    "unsafe": "refuse_unsafe",
    "unanswerable": "refuse_unanswerable",
    "invalid": "refuse_unanswerable",
}


def to_prediction(case_id: str, r: AgentResult) -> Prediction:
    pred = Prediction(
        case_id=case_id,
        decision="error",
        sql=r.sql,
        assumptions=r.assumptions,
        error_code=(r.error or "").split(":")[0] or None,
        error_message=r.error,
        usages=[c.usage for c in r.llm_calls],
        call_steps=[c.node for c in r.llm_calls],
        latency_ms=r.elapsed_ms,
        repairs=r.repairs,
    )
    if r.status == "refused" and r.refusal:
        pred.decision = _REFUSAL_DECISION[r.refusal.kind]  # type: ignore[assignment]
        pred.reason = r.refusal.reason
    elif r.status in ("answered", "partial") and r.sql is not None:
        pred.decision = "answer"
        pred.executed = True
        pred.columns, pred.rows, pred.truncated = r.columns, r.rows, r.truncated
        pred.answer = r.answer if r.status == "answered" else None
        pred.model_text = r.model_text
        if r.status == "partial":
            pred.error_code, pred.error_message = "budget_stop", r.stop_reason
    elif r.status == "partial":
        pred.error_code, pred.error_message = "budget_stop", r.stop_reason
    return pred


class AgentSystem:
    def __init__(self, agent: Agent):
        self.agent = agent
        self.llm = agent.deps.llm
        self.name = agent.deps.config.variant()
        if agent.deps.config.as_of != AS_OF_DATE:
            raise ValueError(f"The agent's as-of date must be {AS_OF_DATE} for evals")

    def run(self, case: EvalCase) -> Prediction:
        return to_prediction(case.id, self.agent.ask(case.question, case.scope))
