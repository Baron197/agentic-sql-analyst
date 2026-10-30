"""Rate limit and daily budget (429), kill switch (503). No paid call is ever made."""

import psycopg
import pytest

from backend.tests.api.conftest import ANALYST, MANAGER, sign_in
from sql_analyst.api.ratelimit import SlidingWindowLimiter
from sql_analyst.config import get_settings

Q = {"question": "Delete all orders from 2024."}  # refused by the guard: fast, no query
SPEND_ROW = """
INSERT INTO app.runs (run_id, user_id, status, question, provider, model, keyless, llm_calls,
    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd, elapsed_ms, record)
VALUES (%s, %s, 'answered', 'q', 'openai', 'm', false, 1, 0, 0, 0, 0, %s, 1.0, %s)
"""


@pytest.mark.db
def test_rate_limit_per_user(client, override):
    override(rate_limit_per_minute=2)
    sign_in(client, ANALYST)
    assert [client.post("/api/ask", json=Q).status_code for _ in range(2)] == [200, 200]
    r = client.post("/api/ask/stream", json=Q)  # the stream shares the same limit
    assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"
    assert 0 < int(r.headers["Retry-After"]) <= 61
    assert sign_in(client, MANAGER).post("/api/ask", json=Q).status_code == 200  # per user


@pytest.fixture
def spent_today():
    """A stored run that cost $5 today (deleted afterwards)."""
    admin = get_settings().admin_conninfo()
    with psycopg.connect(admin) as conn:
        conn.execute(SPEND_ROW, ("test-spend", ANALYST, 5.0, "{}"))
    yield 5.0
    with psycopg.connect(admin) as conn:
        conn.execute("DELETE FROM app.runs WHERE run_id = 'test-spend'")


@pytest.mark.db
def test_daily_budget_cap_returns_429(client, override, spent_today, resources):
    assert resources.store.spent_today_usd() >= spent_today
    override(daily_budget_usd=1.0)
    r = sign_in(client).post("/api/ask", json=Q)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "daily_budget_reached"
    override(daily_budget_usd=100.0)
    assert client.post("/api/ask", json=Q).status_code == 200


@pytest.mark.db
def test_kill_switch_returns_503_when_a_paid_model_is_configured(
    client, override, resources, monkeypatch
):
    monkeypatch.setattr(resources.agent.deps.llm, "provider", "openai")  # pretend it is live
    called = []
    monkeypatch.setattr(resources.agent, "ask", lambda *a: called.append(a))
    monkeypatch.setattr(resources.agent, "stream", lambda *a: called.append(a))
    override(live_mode_enabled=False)
    sign_in(client)
    for path in ("/api/ask", "/api/ask/stream"):
        r = client.post(path, json=Q)
        assert r.status_code == 503 and r.json()["detail"]["code"] == "live_mode_disabled"
    assert called == []
    assert client.get("/api/health").json()["mode"] == "live"


@pytest.mark.db
def test_keyless_mode_ignores_the_kill_switch(client, override):
    override(live_mode_enabled=False)
    assert sign_in(client).post("/api/ask", json=Q).status_code == 200


def test_sliding_window_limiter_forgets_old_hits():
    now = [0.0]
    limiter = SlidingWindowLimiter(2, window_s=60, clock=lambda: now[0])
    assert limiter.allow("a") and limiter.allow("a") and not limiter.allow("a")
    assert limiter.allow("b")
    now[0] = 59.9
    assert not limiter.allow("a") and limiter.retry_after_s("a") == 1
    now[0] = 60.0
    assert limiter.allow("a")
