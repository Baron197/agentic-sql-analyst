"""Keyless end to end: every demo question through the real pipeline (database, RLS, index).

Only the model is replaced (by the rule-based keyless responder). This shows the plumbing
works; it says nothing about how well a real model answers.
"""

import json

import pytest

from sql_analyst.agent.factory import build_agent
from sql_analyst.agent.keyless import load_demo
from sql_analyst.config import get_settings
from sql_analyst.dictionary.loader import load_dictionary
from sql_analyst.safety.executor import Executor
from sql_analyst.users import DEMO_USERS

pytestmark = pytest.mark.db

DEMO = load_demo()
CASES = [(d, user) for d in DEMO for user in d.users]
JABODETABEK_CITIES = {"Jakarta", "Bogor", "Depok", "Tangerang", "Bekasi"}


@pytest.fixture(scope="module")
def agent(tmp_path_factory):
    settings = get_settings().model_copy(update={"runs_dir": str(tmp_path_factory.mktemp("runs"))})
    with Executor.from_settings(settings, load_dictionary()) as ex:
        yield build_agent(settings, ex)


@pytest.mark.parametrize(("demo", "user"), CASES, ids=[f"{d.id}-{u}" for d, u in CASES])
def test_demo_question_runs_end_to_end(agent, demo, user):
    r = agent.ask(demo.question, DEMO_USERS[user])
    assert r.usage.keyless and r.usage.cost_usd == 0
    if demo.expected == "refuse_unsafe":
        assert r.status == "refused" and r.refusal.kind == "unsafe" and r.sql is None
        return
    if demo.expected == "refuse_unanswerable":
        assert r.status == "refused" and r.refusal.kind == "unanswerable" and r.sql is None
        assert r.suggestions == demo.suggestions and r.refusal.reason == demo.reason
        return
    assert r.status == "answered", (r.error, r.trace)
    assert r.row_count > 0 and not r.truncated and r.repairs == 0
    assert "{{" not in r.answer and not r.answer_fallback
    assert r.model_text is not None and not any(
        ch.isdigit()
        for ch in r.model_text.replace("2025", "").replace("2026", "").replace("Q1", "")
    )
    assert r.chart.type == demo.chart.type
    assert r.lang == demo.lang


def test_manager_sees_only_jabodetabek_stores(agent):
    question = next(d.question for d in DEMO if d.id == "demo05")
    everyone = agent.ask(question, DEMO_USERS["analyst"])
    manager = agent.ask(question, DEMO_USERS["manager_jakarta"])
    assert 0 < manager.row_count < everyone.row_count
    cities = {name.split()[1] for name, _orders in manager.rows}  # "Arunika <City> <Area>"
    assert cities <= JABODETABEK_CITIES


def test_runs_are_saved_to_the_run_store(agent):
    r = agent.ask(DEMO[0].question, DEMO_USERS["analyst"])
    lines = (agent.deps.run_store.directory).glob("*.jsonl")
    records = [
        json.loads(line) for path in lines for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert r.run_id in {rec["run_id"] for rec in records}


def test_unknown_question_is_declined_in_keyless_mode(agent):
    r = agent.ask("Which supplier has the longest lead time?", DEMO_USERS["analyst"])
    assert r.status == "refused" and "Keyless mode" in r.refusal.reason
