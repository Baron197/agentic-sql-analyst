"""GET /api/runs and GET /api/runs/{run_id}: the signed-in user's own runs only."""

from typing import Any

from fastapi import APIRouter, Query

from sql_analyst.api.auth import CurrentUser, Res
from sql_analyst.api.deps import api_error

router = APIRouter(prefix="/api", tags=["runs"])


@router.get("/runs")
def list_runs(user: CurrentUser, res: Res, limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    return {"runs": res.store.runs(user.user_id, limit)}


@router.get("/runs/{run_id}")
def get_run(run_id: str, user: CurrentUser, res: Res) -> dict[str, Any]:
    record = res.store.run(run_id, user.user_id)
    if record is None:  # also for another user's run: no hint that it exists
        raise api_error(404, "not_found", "No such run.")
    return record
