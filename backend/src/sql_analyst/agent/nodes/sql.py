"""generate_sql, validate_sql, execute, and the repair rule they share."""

import re
from typing import Any

from sql_analyst.agent.deps import AgentDeps, call_llm
from sql_analyst.agent.guard import check_question
from sql_analyst.agent.nodes.retrieve import render_context
from sql_analyst.agent.schemas import SQLDraft
from sql_analyst.agent.state import AgentState, Refusal, ResultTable, SQLAttempt
from sql_analyst.agent.texts import text
from sql_analyst.safety.errors import SafetyError, SQLRejected

SQL_MAX_TOKENS = 8_000


def fail(
    state: AgentState, deps: AgentDeps, stage: str, sql: str | None, code: str, message: str
) -> dict[str, Any]:
    """Record a failed attempt and send the run back to generate_sql if repairs remain.

    With no repairs left: if an earlier attempt produced a result (check_result asked for a
    retry), answer from that result with a caveat; otherwise end the run with an error.
    """
    attempt = SQLAttempt(sql=sql, stage=stage, ok=False, error_code=code, error=message)  # type: ignore[arg-type]
    update: dict[str, Any] = {"sql_attempts": [attempt]}
    if deps.config.repair and state.repairs < deps.config.limits.max_repairs:
        return update | {
            "feedback": message,
            "repairs": state.repairs + 1,
            "goto": "generate_sql",
            "_note": f"{code}: repair {state.repairs + 1}",
        }
    if state.result is not None:
        return update | {
            "feedback": None,
            "caveats": [*state.caveats, text("caveat_retry_failed", state.lang)],
            "goto": "write_answer",
            "_note": f"{code}: no repairs left, keeping the earlier result",
        }
    return update | {
        "feedback": None,
        "status": "error",
        "error": f"{code}: {message}",
        "goto": "finalize",
        "_note": f"{code}: no repairs left",
    }


MAX_SUGGESTIONS = 3
_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def clean_suggestions(raw: list[str], deps: AgentDeps) -> list[str]:
    """Follow-up questions offered with a refusal (docs/DECISIONS.md D040).

    They are model text shown as clickable questions. Kept only if short, safe to ask (the
    input guard passes them), and any year they name is inside the data window. No query
    ran, so they cannot quote a result.
    """
    window = deps.dictionary.data_window
    years = set(range(window.start.year, window.end.year + 1))
    out: list[str] = []
    for raw_text in raw:
        s = " ".join(raw_text.split())
        if not s or len(s) > 200 or s in out or check_question(s) is not None:
            continue
        if any(int(m.group(0)) not in years for m in _YEAR.finditer(s)):
            continue
        out.append(s)
        if len(out) == MAX_SUGGESTIONS:
            break
    return out


def _user_message(state: AgentState, deps: AgentDeps) -> str:
    scope = state.user
    access = (
        "all regions"
        if scope.region_ids == "all"
        else "some regions only (enforced by the database)"
    )
    question = " ".join(state.question.split())
    parts = []
    if state.context:
        context = render_context(state.context, deps)
        if context:
            parts.append(f"<context>\n{context}\n</context>")
    parts.append(
        f"As-of date (today): {deps.config.as_of}. The user is a {scope.role} with access to {access}."
    )
    parts.append(f"Question: {question}")
    failed = [a for a in state.sql_attempts if not a.ok]
    if failed:
        parts.append("Previous attempts failed. Fix the last error:")
        for i, a in enumerate(failed, start=1):
            parts.append(f"Attempt {i} SQL:\n{a.sql or '(none)'}\nError ({a.stage}): {a.error}")
    return "\n\n".join(parts)


def generate_sql(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    draft, calls, error = call_llm(
        deps, "generate_sql", deps.sql_system, _user_message(state, deps), SQLDraft, SQL_MAX_TOKENS
    )
    update: dict[str, Any] = {"llm_calls": calls, "feedback": None}
    if draft is None:
        return update | {
            "status": "error",
            "error": f"llm_error: {error}",
            "goto": "finalize",
            "_note": "model call failed",
        }
    if draft.decision != "answer":
        kind = "unsafe" if draft.decision == "refuse_unsafe" else "unanswerable"
        suggestions = clean_suggestions(draft.suggestions, deps) if kind == "unanswerable" else []
        return update | {
            "refusal": Refusal(kind=kind, reason=draft.reason or draft.decision, source="model"),
            "suggestions": suggestions,
            "status": "refused",
            "goto": "refuse",
            "_note": draft.decision,
        }
    if not draft.sql or not draft.sql.strip():
        return update | fail(
            state, deps, "generate", None, "no_sql", "decision=answer but no SQL was given."
        )
    return update | {
        "draft_sql": draft.sql,
        "assumptions": draft.assumptions,
        "confidence": draft.confidence,
        "_note": f"confidence {draft.confidence}",
    }


def validate_sql(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    try:
        validated = deps.validator.validate(state.draft_sql or "")
    except SQLRejected as e:
        return fail(state, deps, "validate", state.draft_sql, e.code, e.message)
    return {"validated_sql": validated.sql, "_note": ", ".join(sorted(validated.views))}


def execute(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    """Run as the user's signed scope. Validated again here: the executor never trusts state."""
    try:
        validated = deps.validator.validate(state.validated_sql or "")
        r = deps.executor.run_validated(validated, state.user)
    except SafetyError as e:
        return fail(state, deps, "execute", state.validated_sql, e.code, e.message)
    result = ResultTable(
        columns=r.columns,
        rows=r.rows,
        row_count=r.row_count,
        truncated=r.truncated,
        plan_cost=r.plan_cost,
        elapsed_ms=r.elapsed_ms,
    )
    return {
        "result": result,
        "sql": r.sql,
        "_note": f"{r.row_count} rows{' (truncated)' if r.truncated else ''}, cost {r.plan_cost:,.0f}",
    }
