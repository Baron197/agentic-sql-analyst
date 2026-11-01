"""Tables for docs/EVAL_RESULTS.md, built only from committed result files.

    uv run python -m eval.report eval/results/<a>.json eval/results/<b>.json ...

Every row links to the file it came from, so no number in the write-up is typed by hand.
"""

import json
import sys
from pathlib import Path
from typing import Any

DOCS_TO_RESULTS = "../eval/results/"

COLUMNS = [
    ("EX strict", "ex_strict"),
    ("EX lenient", "ex_lenient"),
    ("EX relabeled", "ex_relabeled"),
    ("Valid SQL", "valid_sql_rate"),
    ("Repairs", "repair_rate"),
    ("Refusal acc.", "refusal_accuracy"),
    ("Unsafe refused", "unsafe_refusal_rate"),
    ("Safety block", "safety_block_rate"),
    ("Typed numbers", "grounding_violations"),
    ("p50 s", "latency_p50_ms"),
    ("p95 s", "latency_p95_ms"),
    ("$ / question", "cost_per_question_usd"),
    ("Cache hit", "cache_hit_rate"),
]


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def cell(stat: dict[str, float | None], key: str, repeats: int) -> str:
    mean, std = stat["mean"], stat["std"]
    if mean is None:
        return "n/a"
    if key.startswith("latency"):
        mean, std = mean / 1000, (std or 0) / 1000
        fmt = "{:.1f}"
    elif key == "cost_per_question_usd":
        fmt = "{:.5f}"
    elif key == "grounding_violations":
        fmt = "{:.1f}" if std else "{:.0f}"
    else:
        fmt = "{:.3f}"
    shown = fmt.format(mean)
    return f"{shown} ± {fmt.format(std)}" if repeats > 1 else shown


def summary_table(paths: list[Path]) -> str:
    head = (
        ["System", "Model", "Questions x repeats"] + [c for c, _ in COLUMNS] + ["Total $", "File"]
    )
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for p in paths:
        r = load(p)
        m, a = r["meta"], r["aggregate"]
        missing = {"mean": None, "std": None}  # older files lack newer metrics
        cells = [cell(a.get(k, missing), k, m["repeats"]) for _, k in COLUMNS]
        total = sum(c["cost_usd"] for c in r["cases"])
        lines.append(
            f"| {m['system']} | {m['model']} | {m['n_questions']} x {m['repeats']} | "
            + " | ".join(cells)
            + f" | {total:.4f} | [{p.stem}]({DOCS_TO_RESULTS}{p.name}) |"
        )
    return "\n".join(lines)


def category_table(paths: list[Path], metric: str = "ex_relabeled") -> str:
    """EX by category, averaged over every repeat of each run."""
    rows: dict[str, dict[str, list[bool]]] = {}
    names = []
    for p in paths:
        r = load(p)
        name = f"{r['meta']['system']} ({r['meta']['model']})"
        names.append(name)
        for c in r["cases"]:
            if c.get(metric) is not None:
                rows.setdefault(c["category"], {}).setdefault(name, []).append(bool(c[metric]))
    lines = ["| Category | " + " | ".join(names) + " |", "|" + "---|" * (len(names) + 1)]
    for cat in sorted(rows):
        vals = []
        for n in names:
            flags = rows[cat].get(n, [])
            vals.append(f"{sum(flags) / len(flags):.2f} ({len(flags)})" if flags else "n/a")
        lines.append(f"| {cat} | " + " | ".join(vals) + " |")
    return "\n".join(lines)


def relabeled_only(paths: list[Path]) -> str:
    lines = []
    for p in paths:
        r = load(p)
        ids = sorted({c for rep in r["per_repeat"] for c in rep.get("relabeled_only", [])})
        if ids:
            lines.append(f"- {r['meta']['system']} ({r['meta']['model']}): " + ", ".join(ids))
    return "\n".join(lines) or "- none"


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv]
    print(summary_table(paths))
    print()
    print(category_table(paths))
    print()
    print(relabeled_only(paths))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
