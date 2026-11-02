"""Data for the web app's public Evaluation page, built only from committed result files (D050).

    uv run poe eval-summary   # writes data/eval_summary.json

The API serves the file at GET /api/eval-summary. It holds the test-split runs reported in
docs/EVAL_RESULTS.md, each with the name of its result file; a test checks that the committed
summary still matches those files, so no number on the page is typed by hand.
"""

import json
import statistics
import sys
from pathlib import Path
from typing import Any

from eval.report import cost_by_repeat, load, total_cost
from sql_analyst.llm.pricing import PRICES_AS_OF

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval" / "results"
OUT = ROOT / "data" / "eval_summary.json"

# The reported test-split runs, in the order of docs/EVAL_RESULTS.md.
FILES = [
    "2026-11-01_agent_live_test_gpt-6-luna_n60_r3.json",
    "2026-11-01_baseline_live_test_gpt-6-luna_n60_r3.json",
    "2026-11-01_agent-no-retrieval_live_test_gpt-6-luna_n60_r3.json",
    "2026-11-01_agent-no-repair_live_test_gpt-6-luna_n60_r3.json",
    "2026-11-01_agent-no-few-shot_live_test_gpt-6-luna_n60_r3.json",
    "2026-11-01_agent-critic_live_test_gpt-6-luna_n60_r3.json",
    "2026-11-02_agent_live_test_gpt-4o-mini_n60_r3.json",
]
METRICS = [
    "ex_strict",
    "ex_lenient",
    "ex_relabeled",
    "valid_sql_rate",
    "repair_rate",
    "false_refusal_rate",
    "assumption_rate",
    "refusal_accuracy",
    "unsafe_refusal_rate",
    "safety_block_rate",
    "grounding_violations",
    "latency_p50_ms",
    "latency_p95_ms",
    "cache_hit_rate",
]


def run_summary(path: Path) -> dict[str, Any]:
    r = load(path)
    m, a = r["meta"], r["aggregate"]
    per_q = cost_by_repeat(r)
    return {
        "file": path.name,
        "date": m["date"],
        "commit": m["commit"],
        "system": m["system"],
        "mode": m["mode"],
        "split": m["split"],
        "model": m["model"],
        "n_questions": m["n_questions"],
        "repeats": m["repeats"],
        "metrics": {k: a[k] for k in METRICS},
        # Cost per question: the mean over repeats, and repeat 1 alone (a cold cache: the
        # realistic cost of a new question). Priced from the token counts, like the report.
        "cost_per_question_usd": {
            "mean": round(statistics.mean(per_q), 8),
            "std": round(statistics.stdev(per_q), 8) if len(per_q) > 1 else 0.0,
        },
        "cost_new_question_usd": round(per_q[0], 8),
        "total_cost_usd": round(total_cost(r), 6),
    }


def build(results: Path = RESULTS) -> dict[str, Any]:
    return {"prices_as_of": PRICES_AS_OF, "runs": [run_summary(results / name) for name in FILES]}


def main() -> int:
    text = json.dumps(build(), ensure_ascii=False, indent=1)
    OUT.write_text(text + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(FILES)} runs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
