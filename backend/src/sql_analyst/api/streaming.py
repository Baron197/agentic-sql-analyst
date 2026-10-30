"""Server-sent events for POST /api/ask/stream.

Event order: `step` (one per graph node, sent as soon as it finishes), `sql`, `rows`
(first 200), `answer`, `done`; or `error` instead of answer/done when the run fails.
"""

import json
import logging
from collections.abc import Iterator
from typing import Any

from fastapi.encoders import jsonable_encoder

from sql_analyst.agent.graph import Agent
from sql_analyst.agent.nodes.finalize import AgentResult
from sql_analyst.api.models import STREAM_ROWS, usage_of
from sql_analyst.observability import NodeEvent
from sql_analyst.safety.scope import UserScope

log = logging.getLogger("sql_analyst.api")


def sse(event: str, data: Any) -> str:
    payload = json.dumps(jsonable_encoder(data), ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def ask_events(agent: Agent, question: str, user: UserScope) -> Iterator[str]:
    try:
        result: AgentResult | None = None
        for item in agent.stream(question, user):
            if isinstance(item, NodeEvent):
                yield sse(
                    "step", {"node": item.node, "status": "done", "ms": item.ms, "note": item.note}
                )
            else:
                result = item
        assert result is not None
        log.info(
            "ask finished", extra={"run_id": result.run_id, "status": result.status, "stream": True}
        )
        if result.sql:
            yield sse("sql", {"sql": result.sql})
        if result.columns:
            yield sse(
                "rows",
                {
                    "columns": result.columns,
                    "rows": result.rows[:STREAM_ROWS],
                    "row_count": result.row_count,
                    "truncated": result.truncated,
                },
            )
        if result.status == "error":
            yield sse(
                "error", {"code": "agent_error", "message": result.answer, "run_id": result.run_id}
            )
            return
        yield sse(
            "answer",
            {
                "status": result.status,
                "text": result.answer,
                "assumptions": result.assumptions,
                "caveats": result.caveats,
                "chart": result.chart,
                "refusal_reason": result.refusal.reason if result.refusal else None,
            },
        )
        yield sse("done", {"run_id": result.run_id, "usage": usage_of(result)})
    except Exception:  # the stream has started: report the failure as an event, not a 500
        log.exception("ask stream failed")
        yield sse(
            "error",
            {"code": "internal_error", "message": "Something went wrong. Please try again."},
        )
