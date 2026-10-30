"""Shared API resources (built once at startup) and the guards in front of /api/ask."""

from dataclasses import dataclass, field

from fastapi import HTTPException, Request

from sql_analyst.agent.graph import Agent
from sql_analyst.api.ratelimit import SlidingWindowLimiter
from sql_analyst.api.store import AppStore
from sql_analyst.config import Settings
from sql_analyst.safety.executor import Executor

LOGIN_FAILURES_PER_MINUTE = 5


@dataclass
class Resources:
    settings: Settings
    agent: Agent
    store: AppStore
    executor: Executor | None = None  # owned here when the app built it
    ask_limiter: SlidingWindowLimiter = field(init=False)
    login_limiter: SlidingWindowLimiter = field(init=False)

    def __post_init__(self) -> None:
        self.ask_limiter = SlidingWindowLimiter(self.settings.rate_limit_per_minute)
        self.login_limiter = SlidingWindowLimiter(LOGIN_FAILURES_PER_MINUTE)

    @property
    def live(self) -> bool:
        """True when the agent's model is a paid provider (not the keyless stand-in)."""
        return self.agent.deps.llm.provider != "fake"

    def close(self) -> None:
        self.store.close()
        if self.executor is not None:
            self.executor.close()


def resources(request: Request) -> Resources:
    return request.app.state.resources


def api_error(status: int, code: str, message: str, headers: dict[str, str] | None = None):
    return HTTPException(status, detail={"code": code, "message": message}, headers=headers)


def check_ask_allowed(res: Resources, user_id: str) -> None:
    """Kill switch (503), then the per-user rate limit and the daily spend cap (429)."""
    if res.live and not res.settings.live_mode_enabled:
        raise api_error(
            503,
            "live_mode_disabled",
            "Live mode is switched off (LIVE_MODE_ENABLED=false). Try again later.",
        )
    if not res.ask_limiter.allow(user_id):
        retry = res.ask_limiter.retry_after_s(user_id)
        raise api_error(
            429,
            "rate_limited",
            f"Too many questions: the limit is {res.settings.rate_limit_per_minute} per minute.",
            {"Retry-After": str(retry)},
        )
    if res.store.spent_today_usd() >= res.settings.daily_budget_usd:
        raise api_error(
            429,
            "daily_budget_reached",
            "Today's demo budget has been used up. Please come back tomorrow.",
        )
