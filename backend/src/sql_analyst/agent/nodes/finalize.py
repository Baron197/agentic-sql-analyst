"""budget_stop and finalize: assemble the response and persist the run."""

import time
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from sql_analyst.agent.deps import AgentDeps
from sql_analyst.agent.grounding import typed_numbers
from sql_analyst.agent.nodes.answer import choose_chart
from sql_analyst.agent.render import fill, strip_slots
from sql_analyst.agent.schemas import ChartSpec
from sql_analyst.agent.state import (
    AgentState,
    Refusal,
    RetrievedContext,
    SQLAttempt,
    Status,
)
from sql_analyst.agent.texts import text
from sql_analyst.observability import LLMCall, NodeEvent, UsageTotals, totals

STORED_ROWS = 50  # rows kept in the run store (the API returns the full result)


class AgentResult(BaseModel):
    """Everything a caller (CLI, API, eval) needs from one run."""

    run_id: str
    created_at: str
    question: str
    user_id: str
    role: str
    lang: str
    status: Status
    answer: str | None
    answer_template: str | None
    model_text: str | None  # what the model typed in the answer: template without slots + caveats
    answer_fallback: bool
    assumptions: list[str]
    caveats: list[str]
    sql: str | None
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    chart: ChartSpec | None
    refusal: Refusal | None
    suggestions: list[str]  # follow-up questions offered with an "unanswerable" refusal
    error: str | None
    stop_reason: str | None
    sql_attempts: list[SQLAttempt]
    repairs: int
    context: RetrievedContext | None
    trace: list[NodeEvent]
    llm_calls: list[LLMCall]
    usage: UsageTotals
    provider: str
    model: str
    variant: str
    elapsed_ms: float

    def record(self) -> dict[str, Any]:
        """The JSON stored for the run (rows trimmed)."""
        data = self.model_dump(mode="json")
        data["rows"] = data["rows"][:STORED_ROWS]
        return data


def budget_stop(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    reason = (
        deps.config.limits.exceeded(state.llm_calls, state.started, next_calls_llm=True)
        or "budget limit reached"
    )
    return {"status": "partial", "stop_reason": reason, "_note": reason}


def finalize(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    status, answer = state.status, state.answer
    caveats = list(state.caveats)
    r = state.result
    if status == "partial":
        if r is not None:
            answer = fill(text("table_only", state.lang), r.columns, r.rows, state.lang)
            caveats.append(text("caveat_stopped", state.lang, reason=state.stop_reason or ""))
        else:
            answer = text("stopped", state.lang, reason=state.stop_reason or "")
    elif status == "error":
        answer = text("error", state.lang)
    elif status == "running":  # defensive: every path should have set a final status
        status, answer = "error", text("error", state.lang)

    model_text = None
    if status == "answered":
        model_text = (
            ""
            if state.answer_fallback
            else (
                strip_slots(state.answer_template or "") + " " + " ".join(state.model_caveats)
            ).strip()
        )
        caveats += state.model_caveats

    # Assumptions are model text too: keep those whose digits come from the question or the SQL
    # (dates and limits the query itself uses); drop any other figure.
    grounded = state.question + " " + (state.sql or "")
    assumptions = [a for a in state.assumptions if not typed_numbers(a, grounded)]

    calls = state.llm_calls
    result = AgentResult(
        run_id=state.run_id,
        created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        question=state.question,
        user_id=state.user.user_id,
        role=state.user.role,
        lang=state.lang,
        status=status,
        answer=answer,
        answer_template=state.answer_template,
        model_text=model_text,
        answer_fallback=state.answer_fallback,
        assumptions=assumptions if status in ("answered", "partial") else [],
        caveats=caveats,
        sql=state.sql,
        columns=r.columns if r else [],
        rows=r.rows if r else [],
        row_count=r.row_count if r else 0,
        truncated=r.truncated if r else False,
        chart=state.chart if status == "answered" else (choose_chart(None, r) if r else None),
        refusal=state.refusal,
        suggestions=state.suggestions if status == "refused" else [],
        error=state.error,
        stop_reason=state.stop_reason,
        sql_attempts=state.sql_attempts,
        repairs=state.repairs,
        context=state.context,
        trace=state.trace,
        llm_calls=calls,
        usage=totals(calls),
        provider=deps.llm.provider,
        model=deps.llm.model,
        variant=deps.config.variant(),
        elapsed_ms=round((time.perf_counter() - state.started) * 1000, 1),
    )
    if deps.run_store is not None:
        deps.run_store.save(result.record())
    dropped = len(state.assumptions) - len(assumptions)
    return {
        "status": status,
        "answer": answer,
        "response": result,
        "_note": f"{status}"
        + (f", dropped {dropped} assumption(s) with typed figures" if dropped else ""),
    }
