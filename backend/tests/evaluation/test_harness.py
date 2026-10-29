"""The harness end to end against the database: gold-vs-gold, keyless baseline, live guard."""

import json

import pytest
from pydantic import SecretStr

import eval.run_eval as run_eval
from eval.baseline import BaselineSystem, keyless_responder, render_dictionary
from eval.cases import SPLITS, load_cases
from eval.leakage import load_examples
from sql_analyst.config import get_settings
from sql_analyst.dictionary.loader import load_dictionary
from sql_analyst.llm.fake import FakeLLM
from sql_analyst.safety.executor import Executor
from sql_analyst.safety.scope import UserScope

pytestmark = pytest.mark.db


@pytest.fixture
def results_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(run_eval, "RESULTS_DIR", tmp_path)
    return tmp_path


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_gold_vs_gold_is_100_percent_on_both_splits(results_dir):
    assert run_eval.main(["--system", "gold", "--split", "dev,test"]) == 0
    report = _load(next(results_dir.glob("*.json")))
    agg = report["aggregate"]
    for metric in (
        "ex_strict",
        "ex_lenient",
        "valid_sql_rate",
        "refusal_accuracy",
        "unsafe_refusal_rate",
        "safety_block_rate",
    ):
        assert agg[metric]["mean"] == 1.0, metric
    assert report["meta"]["n_questions"] == sum(len(load_cases(s)) for s in SPLITS)
    assert report["meta"]["db_unchanged"] is True
    assert report["meta"]["label"].startswith("SANITY CHECK")


def test_keyless_baseline_run_completes_and_is_labelled_plumbing_only(results_dir):
    assert (
        run_eval.main(
            [
                "--system",
                "baseline",
                "--mode",
                "keyless",
                "--split",
                "dev",
                "--limit",
                "8",
                "--repeats",
                "2",
            ]
        )
        == 0
    )
    report = _load(next(results_dir.glob("*.json")))
    assert report["meta"]["label"].startswith("PLUMBING ONLY")
    assert report["meta"]["model"] == "fake-keyless"
    assert len(report["cases"]) == 16 and len(report["per_repeat"]) == 2
    assert report["aggregate"]["total_cost_usd"]["mean"] == 0
    md = next(results_dir.glob("*.md")).read_text(encoding="utf-8")
    assert "PLUMBING ONLY" in md and "mean ± std" in md


def test_live_mode_refuses_to_run_without_confirmation(results_dir, monkeypatch, capsys):
    """No API call is made: the run stops after printing the cost estimate."""
    settings = get_settings().model_copy(
        update={"anthropic_api_key": SecretStr("sk-test-not-a-real-key")}
    )
    monkeypatch.setattr(run_eval, "get_settings", lambda: settings)
    assert (
        run_eval.main(["--system", "baseline", "--mode", "live", "--split", "dev", "--limit", "10"])
        == 3
    )
    out = capsys.readouterr().out
    assert "Estimated cost" in out and "--confirm-live" in out
    assert not list(results_dir.iterdir())


def test_agent_system_is_not_available_before_phase_4(results_dir):
    with pytest.raises(SystemExit):
        run_eval.main(["--system", "agent", "--split", "dev"])


def test_baseline_prompt_contains_the_dictionary_but_no_eval_questions():
    prompt = render_dictionary(load_dictionary())
    assert "analytics.fact_orders" in prompt and "net_revenue" in prompt
    for split in SPLITS:
        for case in load_cases(split):
            assert case.question not in prompt


def test_baseline_pipeline_runs_sql_and_writes_an_answer():
    settings = get_settings()
    with Executor.from_settings(settings, load_dictionary()) as ex:
        system = BaselineSystem(FakeLLM(keyless_responder), ex, load_dictionary())
        case = load_cases("dev")[0]
        pred = system.run(case)
    assert pred.decision == "answer" and pred.executed and pred.answer
    assert len(pred.usages) == 2 and all(u.keyless for u in pred.usages)


@pytest.mark.parametrize("example", [e for e in load_examples() if e.sql], ids=lambda e: e.id)
def test_every_example_sql_runs(example):
    analyst = UserScope(user_id="tests", role="analyst", region_ids="all")
    with Executor.from_settings(get_settings(), load_dictionary()) as ex:
        result = ex.run(example.sql, analyst)
    assert not result.truncated
