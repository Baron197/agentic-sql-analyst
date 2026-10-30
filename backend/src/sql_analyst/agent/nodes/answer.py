"""write_answer (the model writes a template) and render_numbers (code fills it in)."""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sql_analyst.agent import prompts
from sql_analyst.agent.deps import AgentDeps, call_llm
from sql_analyst.agent.render import RenderError, column_kind, fill, grounding_problems
from sql_analyst.agent.schemas import AnswerDraft, ChartSpec
from sql_analyst.agent.state import AgentState, ResultTable
from sql_analyst.agent.texts import text

ANSWER_MAX_TOKENS = 4_000
MAX_ANSWER_ATTEMPTS = 2  # write_answer retries once, then the answer is the table only
_LANG_NAME = {"en": "English", "id": "Bahasa Indonesia"}


def _result_payload(r: ResultTable, limit: int) -> str:
    """Rows as delimited JSON data. '<' and '>' are escaped so a value cannot close the tag."""
    rows = [
        {"r": i, **dict(zip(r.columns, row, strict=True))} for i, row in enumerate(r.rows[:limit])
    ]
    payload = json.dumps(
        {"row_count": r.row_count, "truncated": r.truncated, "rows": rows},
        default=str,
        ensure_ascii=False,
    )
    return payload.replace("<", "\\u003c").replace(">", "\\u003e")


def _message(state: AgentState, deps: AgentDeps) -> str:
    r = state.result
    assert r is not None
    parts = [
        f"Question: {' '.join(state.question.split())}",
        f"Answer in: {_LANG_NAME[state.lang]}",
    ]
    if state.assumptions:
        parts.append(
            "Assumptions the query made:\n" + "\n".join(f"- {a}" for a in state.assumptions)
        )
    parts.append(f"SQL that produced the result:\n{state.sql}")
    parts.append("Result columns: " + ", ".join(r.columns))
    shown = min(r.row_count, deps.config.answer_rows)
    parts.append(
        f'<query_result rows_shown="{shown}">\n{_result_payload(r, deps.config.answer_rows)}\n</query_result>'
    )
    if state.answer_feedback:
        parts.append(
            f"Your previous template was rejected: {state.answer_feedback} Write it again."
        )
    return "\n\n".join(parts)


def write_answer(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    draft, calls, error = call_llm(
        deps,
        "write_answer",
        prompts.load("answer_system"),
        _message(state, deps),
        AnswerDraft,
        ANSWER_MAX_TOKENS,
    )
    update: dict[str, Any] = {"llm_calls": calls, "answer_attempts": state.answer_attempts + 1}
    if draft is None:
        return update | _table_only(state) | {"_note": f"model call failed: {(error or '')[:80]}"}
    return update | {
        "answer_template": draft.template,
        "model_caveats": draft.caveats,
        "chart": draft.chart,
        "answer_feedback": None,
    }


def render_numbers(state: AgentState, deps: AgentDeps) -> dict[str, Any]:
    """Fill the slots. Reject any digit the model typed that the question does not contain."""
    if state.answer_fallback:
        return {}
    r = state.result
    assert r is not None and state.answer_template is not None
    typed = grounding_problems(state.answer_template, state.model_caveats, state.question)
    feedback = None
    if typed:
        feedback = (
            f"It typed numbers itself ({', '.join(typed)}). Every value from the result must be "
            "a slot; refer to periods with the question's own words."
        )
    else:
        try:
            answer = fill(state.answer_template, r.columns, r.rows, state.lang)
        except RenderError as e:
            feedback = str(e)
    if feedback:
        if state.answer_attempts < MAX_ANSWER_ATTEMPTS:
            return {"answer_feedback": feedback, "goto": "write_answer", "_note": feedback[:100]}
        return _table_only(state) | {"_note": f"fallback: {feedback[:80]}"}
    return {
        "answer": answer,
        "chart": choose_chart(state.chart, r),
        "status": "answered",
        "_note": "grounded",
    }


def _table_only(state: AgentState) -> dict[str, Any]:
    r = state.result
    assert r is not None
    return {
        "answer": fill(text("table_only", state.lang), r.columns, r.rows, state.lang),
        "answer_fallback": True,
        "model_caveats": [],
        "caveats": [*state.caveats, text("caveat_fallback", state.lang)],
        "chart": choose_chart(None, r),
        "status": "answered",
        "goto": "finalize",
    }


# -- chart ---------------------------------------------------------------------------
def _is_measure(r: ResultTable, j: int) -> bool:
    values = [row[j] for row in r.rows if row[j] is not None]
    return (
        bool(values)
        and all(isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) for v in values)
        and column_kind(r.columns[j]) != "plain"
    )


def _is_time(r: ResultTable, j: int) -> bool:
    values = [row[j] for row in r.rows if row[j] is not None]
    name = r.columns[j].lower()
    return any(isinstance(v, (date, datetime)) for v in values) or any(
        k in name for k in ("date", "month", "week", "day", "year", "quarter", "period")
    )


def choose_chart(spec: ChartSpec | None, r: ResultTable) -> ChartSpec:
    """Use the model's chart if it fits the result; otherwise pick one from the result's shape."""
    cols = r.columns
    measures = [j for j in range(len(cols)) if _is_measure(r, j)]
    if spec is not None:
        if spec.type == "table":
            return spec
        y_ok = spec.y in cols and cols.index(spec.y) in measures
        x_ok = spec.type == "kpi" or (spec.x in cols and spec.x != spec.y)
        if y_ok and x_ok:
            return spec
    if not measures or r.row_count == 0:
        return ChartSpec(type="table")
    y = cols[measures[0]]
    if r.row_count == 1:
        return ChartSpec(type="kpi", y=y)
    dims = [j for j in range(len(cols)) if j not in measures]
    if not dims:
        return ChartSpec(type="table")
    x = dims[0]
    if _is_time(r, x):
        return ChartSpec(type="line", x=cols[x], y=y)
    return ChartSpec(type="bar", x=cols[x], y=y) if r.row_count <= 50 else ChartSpec(type="table")
