"""data/eval_summary.json (the web app's Evaluation page) must match the committed results."""

import json

from eval import summary


def test_the_committed_summary_matches_the_result_files():
    committed = json.loads(summary.OUT.read_text(encoding="utf-8"))
    assert committed == summary.build(), "run `uv run poe eval-summary` and commit the file"


def test_the_summary_holds_only_live_test_split_runs_with_repeats():
    runs = summary.build()["runs"]
    assert [r["system"] for r in runs[:2]] == ["agent", "baseline"]
    for r in runs:
        assert (r["mode"], r["split"], r["n_questions"], r["repeats"]) == ("live", "test", 60, 3)
        assert r["cost_new_question_usd"] > 0 and r["metrics"]["ex_relabeled"]["std"] is not None
