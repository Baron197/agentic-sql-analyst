"""Tables for docs/EVAL_RESULTS.md, built only from committed result files.

    uv run python -m eval.report eval/results/<a>.json eval/results/<b>.json ...

Every row links to the file it came from, so no number in the write-up is typed by hand.
Costs are priced from each file's token counts with today's table in llm/pricing.py, not
read from the files' own cost fields, which used the prices known on the run date (D053).
"""

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from sql_analyst.llm.pricing import cost_usd

DOCS_TO_RESULTS = "../eval/results/"

QUALITY = [
    ("EX strict", "ex_strict"),
    ("EX lenient", "ex_lenient"),
    ("EX relabeled", "ex_relabeled"),
    ("Valid SQL", "valid_sql_rate"),
    ("Repairs", "repair_rate"),
    ("False refusals", "false_refusal_rate"),
    ("Assumption stated", "assumption_rate"),
    ("Refusal acc.", "refusal_accuracy"),
    ("Unsafe refused", "unsafe_refusal_rate"),
    ("Safety block", "safety_block_rate"),
    ("Typed numbers", "grounding_violations"),
]
SPEED = [("p50 s", "latency_p50_ms"), ("p95 s", "latency_p95_ms"), ("Cache hit", "cache_hit_rate")]


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
        fmt = "{:.6f}"
    elif key == "grounding_violations":
        fmt = "{:.1f}" if std else "{:.0f}"
    else:
        fmt = "{:.3f}"
    shown = fmt.format(mean)
    return f"{shown} ± {fmt.format(std)}" if repeats > 1 else shown


def _link(p: Path) -> str:
    return f"[{p.stem}]({DOCS_TO_RESULTS}{p.name})"


def _name(r: dict[str, Any]) -> str:
    m = r["meta"]
    return f"{m['system']} | {m['model']} | {m['n_questions']} x {m['repeats']}"


def _table(head: list[str], rows: list[str]) -> str:
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head), *rows])


def _missing() -> dict[str, None]:
    return {"mean": None, "std": None}  # older files lack newer metrics


def case_cost(case: dict[str, Any], model: str) -> float:
    """A case's cost at today's prices, from its token counts (call by call when the file has
    them, so per-call price tiers still apply)."""
    calls = case.get("calls")
    if isinstance(calls, list) and calls:
        return sum(
            cost_usd(model, k["input"], k["output"], k["cache_read"], k["cache_write"])
            for k in calls
        )
    return cost_usd(
        model,
        case["input_tokens"],
        case["output_tokens"],
        case["cache_read_tokens"],
        case["cache_write_tokens"],
    )


def cost_by_repeat(r: dict[str, Any]) -> list[float]:
    """Cost per question in each repeat, from the per-case costs (the aggregate is rounded)."""
    model = r["meta"]["model"]
    by: dict[str, list[float]] = defaultdict(list)
    for c in r["cases"]:
        by[str(c["repeat"])].append(case_cost(c, model))
    return [sum(v) / len(v) for _, v in sorted(by.items())]


def total_cost(r: dict[str, Any]) -> float:
    return sum(case_cost(c, r["meta"]["model"]) for c in r["cases"])


def quality_table(paths: list[Path]) -> str:
    rows = []
    for p in paths:
        r = load(p)
        a, n = r["aggregate"], r["meta"]["repeats"]
        cells = [cell(a.get(k, _missing()), k, n) for _, k in QUALITY]
        rows.append(f"| {_name(r)} | " + " | ".join(cells) + f" | {_link(p)} |")
    head = ["System", "Model", "Questions x repeats"] + [c for c, _ in QUALITY] + ["File"]
    return _table(head, rows)


def cost_table(paths: list[Path]) -> str:
    rows = []
    for p in paths:
        r = load(p)
        a, n = r["aggregate"], r["meta"]["repeats"]
        per_q = cost_by_repeat(r)
        std = statistics.stdev(per_q) if len(per_q) > 1 else 0.0
        cost = cell({"mean": statistics.mean(per_q), "std": std}, "cost_per_question_usd", n)
        cells = [cell(a.get(k, _missing()), k, n) for _, k in SPEED]
        total = total_cost(r)
        rows.append(
            f"| {_name(r)} | " + " | ".join(cells) + f" | {cost} | {total:.4f} | {_link(p)} |"
        )
    head = ["System", "Model", "Questions x repeats"] + [c for c, _ in SPEED]
    return _table([*head, "$ / question", "Total $", "File"], rows)


def repeat_table(paths: list[Path]) -> str:
    """Cache hit and cost per repeat: repeat 1 meets a cold cache, later repeats a warm one."""
    rows = []
    for p in paths:
        r = load(p)
        costs = cost_by_repeat(r)
        for i, (rep, cost) in enumerate(zip(r["per_repeat"], costs, strict=True), start=1):
            hit = rep.get("cache_hit_rate")
            hit_s = "n/a" if hit is None else f"{hit:.3f}"
            rows.append(f"| {_name(r)} | {i} | {hit_s} | {cost:.6f} | {_link(p)} |")
    head = ["System", "Model", "Questions x repeats", "Repeat", "Cache hit", "$ / question", "File"]
    return _table(head, rows)


def step_table(paths: list[Path]) -> str:
    """Tokens and cost by graph step, summed over every repeat."""
    rows = []
    keys = ("calls", "input", "cache_read", "cache_write", "output")
    for p in paths:
        r = load(p)
        steps: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for rep in r["per_repeat"]:
            for step, u in (rep.get("usage_by_step") or {}).items():
                for k in keys:
                    steps[step][k] += u[k]
        for step, u in sorted(steps.items()):
            nums = " | ".join(f"{int(u[k]):,}" for k in keys)
            tokens = [int(u[k]) for k in ("input", "output", "cache_read", "cache_write")]
            cost = cost_usd(r["meta"]["model"], *tokens)
            rows.append(f"| {_name(r)} | {step} | {nums} | {cost:.4f} | {_link(p)} |")
    head = ["System", "Model", "Questions x repeats", "Step", "Calls", "Uncached input"]
    head += ["Cache read", "Cache write", "Output", "Cost $", "File"]
    return _table(head, rows)


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
    lines = []
    for cat in sorted(rows):
        vals = []
        for n in names:
            flags = rows[cat].get(n, [])
            vals.append(f"{sum(flags) / len(flags):.2f} ({len(flags)})" if flags else "n/a")
        lines.append(f"| {cat} | " + " | ".join(vals) + " |")
    return _table(["Category", *names], lines)


def language_table(paths: list[Path], metric: str = "ex_relabeled") -> str:
    """EX by question language (en, id), averaged over every repeat."""
    rows = []
    for p in paths:
        r = load(p)
        by: dict[str, list[bool]] = defaultdict(list)
        for c in r["cases"]:
            if c.get(metric) is not None:
                by[c["lang"]].append(bool(c[metric]))
        vals = [
            f"{sum(by[lang]) / len(by[lang]):.3f} ({len(by[lang])})" if by[lang] else "n/a"
            for lang in ("en", "id")
        ]
        rows.append(f"| {_name(r)} | " + " | ".join(vals) + f" | {_link(p)} |")
    return _table(["System", "Model", "Questions x repeats", "English", "Indonesian", "File"], rows)


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
    tables = [quality_table, cost_table, repeat_table, step_table, category_table]
    for table in [*tables, language_table, relabeled_only]:
        print(table(paths))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
