"""check_result: deterministic sanity checks, then an optional critic call."""

import json
from decimal import Decimal
from typing import Any

from sql_analyst.agent import prompts
from sql_analyst.agent.deps import AgentDeps, call_llm
from sql_analyst.agent.nodes.sql import fail
from sql_analyst.agent.render import column_kind
from sql_analyst.agent.schemas import CriticVerdict
from sql_analyst.agent.state import AgentState, ResultTable, SQLAttempt
from sql_analyst.agent.texts import text

IMPLAUSIBLE = Decimal(10) ** 15  # no column of this company reaches a quadrillion
CRITIC_ROWS = 10


def _numeric(v: Any) -> bool:
    return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)


def result_problems(r: ResultTable, row_limit: int | None = None) -> list[str]:
    """Reasons a result looks wrong. An empty list means it passed."""
    problems = []
    if r.row_count == 0:
        problems.append(
            "The query returned no rows. Check the filters, value spellings, date ranges, and "
            "the WIB conversion. If no rows is the right answer, return the same query."
        )
    else:
        for j, col in enumerate(r.columns):
            values = [row[j] for row in r.rows]
            if all(v is None for v in values):
                problems.append(
                    f"Column {col} is NULL in every row (often a filter that matches nothing "
                    "or a join on the wrong key)."
                )
                continue
            nums = [Decimal(str(v)) for v in values if _numeric(v)]
            if any(abs(n) >= IMPLAUSIBLE for n in nums):
                problems.append(
                    f"Column {col} has implausibly large values; check for join fan-out "
                    "(a join that multiplies rows before aggregating)."
                )
            if column_kind(col) == "count" and any(n < 0 for n in nums):
                problems.append(f"Column {col} looks like a count but has negative values.")
    if r.truncated:
        problems.append(
            f"The result hit the row cap ({row_limit or r.row_count} rows). Aggregate, or use "
            "ORDER BY ... LIMIT if the question asks for the top items."
        )
    return problems


def _critic_message(state: AgentState) -> str:
    r = state.result
    assert r is not None
    payload = json.dumps(
        {"columns": r.columns, "rows": r.rows[:CRITIC_ROWS], "row_count": r.row_count},
        default=str,
    )
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e")
    return (
        f"Question: {state.question}\n\nSQL:\n{state.sql}\n\n"
        f"<query_result>\n{payload}\n</query_result>"
    )


def check_result(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    r = state.result
    assert r is not None
    can_retry = (
        deps.config.repair
        and state.result_checks < deps.config.max_result_checks
        and state.repairs < deps.config.limits.max_repairs
    )
    problems = result_problems(r)
    if problems and can_retry:
        return fail(state, deps, "check", state.sql, "result_check", " ".join(problems)) | {
            "result_checks": state.result_checks + 1
        }

    update: dict[str, Any] = {}
    if not problems and deps.config.critic and can_retry:
        verdict, calls, error = call_llm(
            deps,
            "check_result",
            prompts.load("critic_system"),
            _critic_message(state),
            CriticVerdict,
            max_tokens=2_000,
        )
        update["llm_calls"] = calls
        if verdict is not None and not verdict.ok:
            return (
                update
                | fail(
                    state, deps, "check", state.sql, "critic", verdict.problem or "critic rejected"
                )
                | {"result_checks": state.result_checks + 1}
            )
        update["_note"] = (
            "critic ok" if verdict else f"critic failed, ignored: {(error or '')[:80]}"
        )

    caveats = list(state.caveats)
    if r.row_count == 0:
        caveats.append(text("caveat_empty", state.lang))
    if r.truncated:
        caveats.append(text("caveat_truncated", state.lang))
    attempt = SQLAttempt(sql=state.sql, stage="check", ok=True)
    note = update.get("_note") or ("accepted: " + "; ".join(problems)[:80] if problems else "ok")
    return update | {"sql_attempts": [attempt], "caveats": caveats, "_note": note}
