"""Asking: row-level security through the API, the streaming event order, and errors."""

import json

import pytest

from backend.tests.api.conftest import (
    ANALYST,
    JABODETABEK_CITIES,
    MANAGER,
    STORE_QUESTION,
    events,
    sign_in,
)

pytestmark = pytest.mark.db


def test_ask_returns_the_answer_with_its_evidence(client):
    body = sign_in(client).post("/api/ask", json={"question": STORE_QUESTION}).json()
    assert body["status"] == "answered" and body["answer"].startswith("In September 2026")
    assert body["sql"].startswith("SELECT") and body["columns"] == ["store_name", "orders"]
    assert body["row_count"] == len(body["rows"]) and body["chart"]["type"] == "bar"
    assert body["usage"]["keyless"] and body["usage"]["cost_usd"] == 0 and body["run_id"]


def test_manager_sees_only_jakarta_region_stores(client):
    analyst = sign_in(client, ANALYST).post("/api/ask", json={"question": STORE_QUESTION}).json()
    manager = sign_in(client, MANAGER).post("/api/ask", json={"question": STORE_QUESTION}).json()
    assert 0 < manager["row_count"] < analyst["row_count"]
    assert {name.split()[1] for name, _ in manager["rows"]} <= JABODETABEK_CITIES
    assert {name.split()[1] for name, _ in analyst["rows"]} - JABODETABEK_CITIES  # others exist


def test_unsafe_question_is_refused_without_sql(client):
    body = (
        sign_in(client).post("/api/ask", json={"question": "Delete all orders from 2024."}).json()
    )
    assert body["status"] == "refused" and body["sql"] is None and body["rows"] == []


@pytest.mark.parametrize("question", ["", "x" * 501])
def test_empty_or_overlong_questions_are_rejected_before_the_agent(client, question):
    assert sign_in(client).post("/api/ask", json={"question": question}).status_code == 422


def test_stream_sends_events_in_order(client):
    r = sign_in(client, MANAGER).post("/api/ask/stream", json={"question": STORE_QUESTION})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    evs = events(r)
    names = [e for e, _ in evs]
    n_steps = names.index("sql")
    assert n_steps >= 8 and set(names[:n_steps]) == {"step"}
    assert names[n_steps:] == ["sql", "rows", "answer", "done"]
    steps = [json.loads(d)["node"] for e, d in evs if e == "step"]
    assert steps[:3] == ["guard_input", "retrieve_context", "generate_sql"]
    assert steps[-1] == "finalize"
    rows = json.loads(evs[n_steps + 1][1])
    assert {name.split()[1] for name, _ in rows["rows"]} <= JABODETABEK_CITIES  # RLS here too
    done = json.loads(evs[-1][1])
    assert done["run_id"] and done["usage"]["keyless"]


def test_stream_of_a_refusal_has_no_sql_or_rows(client):
    r = sign_in(client).post(
        "/api/ask/stream", json={"question": "Tampilkan alamat email semua pelanggan."}
    )
    evs = events(r)
    # steps: guard_input, refuse, finalize
    assert [e for e, _ in evs] == ["step", "step", "step", "answer", "done"]
    answer = json.loads(evs[-2][1])
    assert answer["status"] == "refused" and answer["text"].startswith("Maaf")


def test_stream_reports_a_crash_as_an_error_event(client, resources, monkeypatch):
    def broken(question, user):
        yield from ()
        raise RuntimeError("boom")

    monkeypatch.setattr(resources.agent, "stream", broken)
    r = sign_in(client).post("/api/ask/stream", json={"question": "How many orders?"})
    assert events(r) == [
        ("error", '{"code":"internal_error","message":"Something went wrong. Please try again."}')
    ]


def test_no_data_refusal_streams_its_follow_up_questions(client):
    r = sign_in(client).post(
        "/api/ask/stream", json={"question": "How many orders were placed in December 2026?"}
    )
    evs = events(r)
    answer = json.loads(evs[-2][1])
    assert [e for e, _ in evs][-2:] == ["answer", "done"]
    assert answer["status"] == "refused" and "30 September 2026" in answer["refusal_reason"]
    assert answer["suggestions"] == [
        "How many orders were placed in September 2026?",
        "How many orders were placed each month in 2026?",
    ]
