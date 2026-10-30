"""API test setup: one keyless app for the module, real database, index, and run store.

Runs created by the tests are deleted afterwards. Settings changes (limits, kill switch)
are made per test with `override` and undone after it.
"""

from datetime import UTC, datetime

import psycopg
import pytest
from fastapi.testclient import TestClient

from sql_analyst.api.deps import Resources
from sql_analyst.api.main import build_resources, create_app
from sql_analyst.config import get_settings

ANALYST = "analyst@demo"
MANAGER = "manager.jakarta@demo"
STORE_QUESTION = "How many orders did each store get in September 2026?"
JABODETABEK_CITIES = {"Jakarta", "Bogor", "Depok", "Tangerang", "Bekasi"}


def password(user_id: str) -> str:
    s = get_settings()
    secret = s.demo_analyst_password if user_id == ANALYST else s.demo_manager_password
    return secret.get_secret_value()


@pytest.fixture(scope="session")
def resources():
    started = datetime.now(UTC)
    res = build_resources(get_settings())
    yield res
    res.close()
    with psycopg.connect(get_settings().admin_conninfo()) as conn:
        conn.execute("DELETE FROM app.runs WHERE created_at >= %s", (started,))


@pytest.fixture
def client(resources: Resources):
    resources.ask_limiter.reset()
    resources.login_limiter.reset()
    with TestClient(create_app(resources=resources)) as c:
        yield c


def sign_in(client: TestClient, user_id: str = ANALYST) -> TestClient:
    r = client.post("/api/auth/login", json={"email": user_id, "password": password(user_id)})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def override(resources: Resources, monkeypatch):
    """override(rate_limit_per_minute=2, ...) changes settings for one test."""

    def apply(**changes):
        monkeypatch.setattr(resources, "settings", resources.settings.model_copy(update=changes))
        resources.__post_init__()  # rebuild the limiters with the new limits

    yield apply
    monkeypatch.undo()
    resources.__post_init__()


def events(response) -> list[tuple[str, str]]:
    """(event, data) pairs from an SSE body."""
    out, name = [], None
    for line in response.text.splitlines():
        if line.startswith("event: "):
            name = line[len("event: ") :]
        elif line.startswith("data: "):
            out.append((name, line[len("data: ") :]))
    return out
