"""GET /api/health (public) and GET /api/metrics (signed in)."""

from typing import Any

from fastapi import APIRouter

from sql_analyst.api.auth import CurrentUser, Res

router = APIRouter(prefix="/api", tags=["operations"])


@router.get("/health")
def health(res: Res) -> dict[str, Any]:
    checks = {"database": False, "run_store": False}
    try:
        with res.agent.deps.executor.pool.connection() as conn:  # type: ignore[attr-defined]
            conn.execute("SELECT 1")
        checks["database"] = True
    except Exception:
        pass
    try:
        res.store.spent_today_usd()
        checks["run_store"] = True
    except Exception:
        pass
    return {
        "status": "ok" if all(checks.values()) else "degraded",
        **checks,
        "mode": "live" if res.live else "keyless",
        "live_mode_enabled": res.settings.live_mode_enabled,
    }


@router.get("/metrics")
def metrics(user: CurrentUser, res: Res) -> dict[str, Any]:
    """Run counts, error rate, latency p50/p95, cost today, and cache use (all users)."""
    return {
        **res.store.metrics(),
        "daily_budget_usd": res.settings.daily_budget_usd,
        "mode": "live" if res.live else "keyless",
    }
