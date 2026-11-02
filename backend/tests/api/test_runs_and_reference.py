"""Run history (own runs only), schema, examples, metrics, and the run store's role."""

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import errors as pg_errors

from backend.tests.api.conftest import ANALYST, MANAGER, STORE_QUESTION, sign_in
from backend.tests.unit.test_recorded import record
from sql_analyst import recorded
from sql_analyst.api.main import create_app
from sql_analyst.config import get_settings
from sql_analyst.db.app_setup import setup_app

pytestmark = pytest.mark.db
REFUSED = {"question": "Delete all orders from 2024."}


def test_runs_are_stored_and_listed_for_their_owner_only(client):
    sign_in(client, MANAGER)
    run_id = client.post("/api/ask", json={"question": STORE_QUESTION}).json()["run_id"]
    runs = client.get("/api/runs").json()["runs"]
    assert runs[0]["run_id"] == run_id and runs[0]["question"] == STORE_QUESTION
    record = client.get(f"/api/runs/{run_id}").json()
    assert record["user_id"] == MANAGER and record["trace"] and record["usage"]["llm_calls"] == 2

    sign_in(client, ANALYST)
    assert run_id not in {r["run_id"] for r in client.get("/api/runs").json()["runs"]}
    other = client.get(f"/api/runs/{run_id}")
    assert other.status_code == 404 and other.json()["detail"]["code"] == "not_found"


def test_demo_sign_ins_share_an_account_but_not_a_history(client, resources, override):
    """Visitors who click "Try as analyst" are the same user; each sees only its own runs."""
    override(demo_login_enabled=True)
    with TestClient(create_app(resources=resources)) as other:
        visitor_runs = []
        for c in (client, other):
            assert c.post("/api/auth/demo", json={"user": "analyst"}).status_code == 200
            visitor_runs.append(c.post("/api/ask", json={"question": STORE_QUESTION}).json())
        mine, theirs = (r["run_id"] for r in visitor_runs)
        assert [r["run_id"] for r in client.get("/api/runs").json()["runs"]] == [mine]
        assert [r["run_id"] for r in other.get("/api/runs").json()["runs"]] == [theirs]
        assert client.get(f"/api/runs/{theirs}").status_code == 404

    # A password sign-in to the same account sees all of its runs, both sessions included.
    sign_in(client, ANALYST)
    assert {mine, theirs} <= {r["run_id"] for r in client.get("/api/runs").json()["runs"]}
    assert client.get(f"/api/runs/{theirs}").json()["session_id"] is not None


def test_schema_and_examples(client):
    sign_in(client, MANAGER)
    schema = client.get("/api/schema").json()
    assert schema["fictional"] and len(schema["views"]) == 22
    assert schema["your_scope"] == {"role": "manager", "region_ids": [1, 2, 3, 4, 5]}
    examples = client.get("/api/examples").json()
    assert examples["keyless"] and len(examples["examples"]) == 9


def test_metrics(client):
    sign_in(client).post("/api/ask", json=REFUSED)
    m = client.get("/api/metrics").json()
    assert m["runs"] >= 1 and m["mode"] == "keyless" and m["latency_p50_ms"] is not None
    assert {"error_rate", "latency_p95_ms", "cost_today_usd", "cache_hit_rate"} <= m.keys()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM analytics.dim_store",
        "SELECT count(*) FROM core.customers",
        "SELECT count(*) FROM retrieval.chunks",
        "UPDATE app.users SET role = 'analyst'",
        "DELETE FROM app.runs",
        "UPDATE app.runs SET cost_usd = 0",
    ],
)
def test_the_run_store_role_can_only_read_users_and_append_runs(sql):
    with (
        psycopg.connect(get_settings().writer_conninfo()) as conn,
        pytest.raises(pg_errors.InsufficientPrivilege),
    ):
        conn.execute(sql)


def test_app_setup_is_idempotent_and_keeps_stored_runs(client):
    sign_in(client).post("/api/ask", json=REFUSED)
    admin = get_settings().admin_conninfo()
    with psycopg.connect(admin) as conn:
        before = conn.execute("SELECT count(*) FROM app.runs").fetchone()[0]
    setup_app(get_settings())
    with psycopg.connect(admin) as conn:
        assert conn.execute("SELECT count(*) FROM app.runs").fetchone()[0] == before
    sign_in(client)  # passwords still work after re-hashing


def test_recorded_runs_are_public(client, tmp_path, monkeypatch):
    monkeypatch.setattr(recorded, "DATA_PATH", tmp_path / "recorded_runs.json")
    assert client.get("/api/recorded-runs").json() == {"runs": []}  # no file yet: empty
    runs = recorded.RecordedRuns()
    recorded.add(runs, [record("r1")])
    recorded.save(runs)
    body = client.get("/api/recorded-runs").json()  # not signed in
    assert [r["run_id"] for r in body["runs"]] == ["r1"] and "user_id" not in body["runs"][0]


def test_eval_summary_is_public(client):
    runs = client.get("/api/eval-summary").json()["runs"]  # not signed in
    assert runs[0]["system"] == "agent" and runs[0]["file"].endswith("_n60_r3.json")
