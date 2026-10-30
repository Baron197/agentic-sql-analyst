"""guard_input and refuse."""

from typing import Any

from sql_analyst.agent import prompts
from sql_analyst.agent.deps import AgentDeps, call_llm
from sql_analyst.agent.guard import check_question, detect_language
from sql_analyst.agent.schemas import GuardVerdict
from sql_analyst.agent.state import AgentState, Refusal
from sql_analyst.agent.texts import text

_LLM_CATEGORY = {
    "write_request": "unsafe",
    "personal_data": "unsafe",
    "off_topic": "unanswerable",
    "unanswerable": "unanswerable",
}


def guard_input(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    """Deterministic checks first, then (optionally) one cheap classification call."""
    update: dict[str, Any] = {"lang": detect_language(state.question)}
    hit = check_question(state.question)
    if hit:
        update.update(
            refusal=Refusal(kind=hit.kind, reason=hit.reason, source="guard"),
            status="refused",
            goto="refuse",
            _note=f"rule {hit.rule}",
        )
        return update
    if deps.config.guard_llm:
        verdict, calls, error = call_llm(
            deps,
            "guard_input",
            prompts.load("guard_system"),
            f"Question: {state.question}",
            GuardVerdict,
            max_tokens=1_000,
        )
        update["llm_calls"] = calls
        if verdict and verdict.category in _LLM_CATEGORY:
            update.update(
                refusal=Refusal(
                    kind=_LLM_CATEGORY[verdict.category],  # type: ignore[arg-type]
                    reason=verdict.reason or verdict.category,
                    source="model",
                ),
                status="refused",
                goto="refuse",
                _note=f"classifier {verdict.category}",
            )
        elif error:
            update["_note"] = f"classifier failed, continuing: {error[:80]}"
    return update


def refuse(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    kind = state.refusal.kind if state.refusal else "unanswerable"
    return {"answer": text(f"refuse_{kind}", state.lang), "status": "refused"}
