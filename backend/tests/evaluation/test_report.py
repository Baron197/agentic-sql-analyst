"""eval/report.py builds the EVAL_RESULTS tables from result files only."""

import json

from eval.report import (
    category_table,
    cost_table,
    language_table,
    quality_table,
    relabeled_only,
    repeat_table,
    step_table,
)


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
    }
    step = {"calls": 2, "input": 10, "cache_read": 2000, "cache_write": 0, "output": 50}
    data = {
        "meta": {"system": system, "model": "m", "n_questions": 2, "repeats": repeats},
        "aggregate": aggregate,
        "per_repeat": [
            {"relabeled_only": ["t001"], "cache_hit_rate": 0.5, "usage_by_step": {"sql": step | {"cost_usd": 0.001}}},
            {"cache_hit_rate": 0.9, "usage_by_step": {"sql": step | {"cost_usd": 0.002}}},
        ],
        "cases": [
            {"repeat": 0, "category": "join", "lang": "en", "ex_relabeled": True, "cost_usd": 0.001},
            {"repeat": 0, "category": "join", "lang": "id", "ex_relabeled": False, "cost_usd": 0.003},
            {"repeat": 1, "category": "adversarial", "lang": "en", "ex_relabeled": None, "cost_usd": 0.0},
            {"repeat": 1, "category": "join", "lang": "en", "ex_relabeled": True, "cost_usd": 0.002},
        ],
    }  # fmt: skip
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_tables_link_every_row_to_its_file_and_show_mean_and_std(tmp_path):
    a = _result(tmp_path, "a.json", "agent")
    b = _result(tmp_path, "b.json", "baseline", repeats=1)
    quality = quality_table([a, b])
    assert "[a](../eval/results/a.json)" in quality and "[b](../eval/results/b.json)" in quality
    assert "0.900 ± 0.020" in quality and "| 0.900 |" in quality  # one repeat: no ± shown
    assert "| n/a |" in quality  # metrics missing from older files
    cost = cost_table([a])
    # $/question per repeat from the cases: 0.002 and 0.001 -> mean 0.0015, sample std 0.000707
    assert "| 7.5 ± 0.1 |" in cost and "0.001500 ± 0.000707" in cost and "| 0.0060 |" in cost
    repeats = repeat_table([a])
    assert "| 1 | 0.500 | 0.002000 |" in repeats and "| 2 | 0.900 | 0.001000 |" in repeats
    assert "| sql | 4 | 20 | 4,000 | 0 | 100 | 0.0030 |" in step_table([a])
    cats = category_table([a])
    assert "| join | 0.67 (3) |" in cats and "adversarial" not in cats
    assert "| 1.000 (2) | 0.000 (1) |" in language_table([a])
    assert relabeled_only([a]) == "- agent (m): t001"
