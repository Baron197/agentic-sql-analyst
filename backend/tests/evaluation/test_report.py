"""eval/report.py builds the EVAL_RESULTS tables from result files only."""

import json

from eval.report import category_table, relabeled_only, summary_table


def _result(tmp_path, name, system, repeats=3):
    stat = {"mean": 0.9, "std": 0.02}
    aggregate = {
        k: stat
        for k in (
            "ex_strict", "ex_lenient", "ex_relabeled", "valid_sql_rate", "repair_rate",
            "refusal_accuracy", "unsafe_refusal_rate", "safety_block_rate", "cache_hit_rate",
        )
    }  # fmt: skip
    aggregate |= {
        "grounding_violations": {"mean": 0, "std": 0},
        "latency_p50_ms": {"mean": 7500, "std": 100},
        "latency_p95_ms": {"mean": 11000, "std": 300},
        "cost_per_question_usd": {"mean": 0.0006, "std": 0.00001},
    }
    data = {
        "meta": {"system": system, "model": "m", "n_questions": 2, "repeats": repeats},
        "aggregate": aggregate,
        "per_repeat": [{"relabeled_only": ["t001"]}],
        "cases": [
            {"category": "join", "ex_relabeled": True, "cost_usd": 0.001},
            {"category": "join", "ex_relabeled": False, "cost_usd": 0.002},
            {"category": "adversarial", "ex_relabeled": None, "cost_usd": 0.0},
        ],
    }
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_tables_link_every_row_to_its_file_and_show_mean_and_std(tmp_path):
    a = _result(tmp_path, "a.json", "agent")
    b = _result(tmp_path, "b.json", "baseline", repeats=1)
    table = summary_table([a, b])
    assert "[a](../eval/results/a.json)" in table and "[b](../eval/results/b.json)" in table
    assert "0.900 ± 0.020" in table and "| 7.5 ± 0.1 |" in table and "0.0030" in table
    assert "| 0.900 |" in table  # one repeat: no ± shown
    cats = category_table([a])
    assert "| join | 0.50 (2) |" in cats and "adversarial" not in cats
    assert relabeled_only([a]) == "- agent (m): t001"
