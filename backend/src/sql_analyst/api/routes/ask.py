"""POST /api/ask and POST /api/ask/stream."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from sql_analyst.api.auth import CurrentUser, Res
from sql_analyst.api.deps import check_ask_allowed
from sql_analyst.api.models import AskRequest, AskResponse, ask_response
from sql_analyst.api.streaming import ask_events

router = APIRouter(prefix="/api", tags=["ask"])
log = logging.getLogger("sql_analyst.api")


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request, user: CurrentUser, res: Res) -> AskResponse:
    """Answer a question as the signed-in user (their region scope applies)."""
    check_ask_allowed(res, user.user_id)
    result = res.agent.ask(body.question, user.scope(), session_id=user.session_id)
    request.state.run_id = result.run_id
    log.info("ask finished", extra={"run_id": result.run_id, "status": result.status})
    return ask_response(result)


@router.post(
    "/ask/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def ask_stream(body: AskRequest, user: CurrentUser, res: Res) -> StreamingResponse:
    """The same run as server-sent events: step..., sql, rows, answer, done (or error)."""
    check_ask_allowed(res, user.user_id)
    return StreamingResponse(
        ask_events(res.agent, body.question, user.scope(), user.session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
