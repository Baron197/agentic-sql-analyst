"""Recorded live runs: real model answers, published so visitors can read them for free (D048).

Runs are copied from the run store (`app.runs`) into `data/recorded_runs.json`, which is
committed. The web app shows them on its public Recorded runs page (`GET /api/recorded-runs`),
and docs/RECORDED_RUNS.md is generated from the same file.

    python -m sql_analyst.recorded dump [--since 2026-11-02] > runs.json  # live runs, as stored
    python -m sql_analyst.recorded add runs.json [--ids ID,ID]  # into the data file + the docs
    python -m sql_analyst.recorded docs                         # regenerate RECORDED_RUNS.md
    python -m sql_analyst.recorded reprice                      # costs at today's prices

`dump` reads the database with the owner login, so run it where the database is. For the
production stack: `infra/compose.sh run --rm -T seed python -m sql_analyst.recorded dump`.
Keyless runs are never published: they replay a script, not a model. The published form
leaves out the user and session ids, the retrieved context, and the per-call details.
Each run's cost is priced from its token counts with llm/pricing.py, so a price correction
reaches the published runs with `reprice` (D053).
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from pydantic import BaseModel, ConfigDict

from sql_analyst.agent.schemas import ChartSpec
from sql_analyst.agent.state import Refusal
from sql_analyst.config import get_settings
from sql_analyst.dictionary.loader import REPO_ROOT
from sql_analyst.llm.pricing import PRICES_AS_OF, cost_usd

DATA_PATH = REPO_ROOT / "data" / "recorded_runs.json"
DOCS_PATH = REPO_ROOT / "docs" / "RECORDED_RUNS.md"
DOC_ROWS = 10  # result rows shown per run in the Markdown page
LANGS = {"en": "English", "id": "Bahasa Indonesia"}
ROLES = {"analyst": "analyst (all regions)", "manager": "Jakarta manager (Jabodetabek only)"}


class TraceStep(BaseModel):
    node: str
    ms: float
    note: str | None = None


class RecordedUsage(BaseModel):
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    keyless: bool


class RecordedRun(BaseModel):
    """The published part of a stored run (`AgentResult.record()`)."""

    model_config = ConfigDict(extra="ignore")

    run_id: str
    created_at: str
    question: str
    lang: str
    role: str
    status: str
    answer: str | None
    assumptions: list[str]
    caveats: list[str]
    sql: str | None
    columns: list[str]
    rows: list[list[Any]]  # the first 50, as stored
    row_count: int
    truncated: bool
    chart: ChartSpec | None
    refusal: Refusal | None
    suggestions: list[str] = []
    repairs: int
    provider: str
    model: str
    trace: list[TraceStep]
    usage: RecordedUsage
    elapsed_ms: float


class RecordedRuns(BaseModel):
    runs: list[RecordedRun] = []


def priced(run: RecordedRun) -> RecordedRun:
    """The run with its cost recomputed from its tokens at today's prices."""
    u = run.usage
    cost = cost_usd(
        run.model, u.input_tokens, u.output_tokens, u.cache_read_tokens, u.cache_write_tokens
    )
    return run.model_copy(update={"usage": u.model_copy(update={"cost_usd": cost})})


def from_record(record: dict[str, Any]) -> RecordedRun:
    run = RecordedRun.model_validate(record)
    if run.usage.keyless:
        raise ValueError(f"run {run.run_id} is keyless: only live model runs are published")
    return priced(run)


def load(path: Path | None = None) -> RecordedRuns:
    path = path or DATA_PATH
    if not path.exists():
        return RecordedRuns()
    return RecordedRuns.model_validate_json(path.read_text(encoding="utf-8"))


def save(recorded: RecordedRuns, path: Path | None = None) -> None:
    recorded.runs.sort(key=lambda r: r.created_at)
    text = json.dumps(recorded.model_dump(mode="json"), ensure_ascii=False, indent=1)
    (path or DATA_PATH).write_text(text + "\n", encoding="utf-8", newline="\n")


def dump(conninfo: str, since: date | None = None) -> list[dict[str, Any]]:
    """Every live (not keyless) run in the store, oldest first, as stored."""
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT record FROM app.runs WHERE NOT keyless "
            "AND (%s::date IS NULL OR created_at >= %s::date) ORDER BY created_at",
            (since, since),
        ).fetchall()
    return [r[0] for r in rows]


def add(
    recorded: RecordedRuns, records: list[dict[str, Any]], ids: set[str] | None = None
) -> list[str]:
    """Add the chosen records (all, or those in `ids`); a run already there is replaced."""
    chosen = [r for r in records if ids is None or r["run_id"] in ids]
    missing = (ids or set()) - {r["run_id"] for r in chosen}
    if missing:
        raise ValueError(f"not in the dump: {', '.join(sorted(missing))}")
    new = [from_record(r) for r in chosen]
    keep = {r.run_id for r in new}
    recorded.runs = [r for r in recorded.runs if r.run_id not in keep] + new
    return [r.run_id for r in new]


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(columns: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(_cell(c) for c in columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def _seconds(ms: float) -> str:
    return f"{ms / 1000:.1f} s" if ms >= 1000 else f"{ms:.0f} ms"


def _model(r: RecordedRun) -> str:
    """The model, or why none was called (a live run the rule-based guard refused, D051)."""
    return f"`{r.model}`" if r.usage.llm_calls else "no model call"


def render_markdown(recorded: RecordedRuns) -> str:
    out = [
        "# Recorded live runs",
        "",
        "<!-- Generated by `uv run poe recorded-docs` from data/recorded_runs.json. "
        "Do not edit by hand. -->",
        "",
        "Real answers from the agent with a live model, recorded in the app and replayed here, "
        "so you can read them without running anything. PT Arunika Niaga and all of its data "
        "are fictional and synthetic.",
        "",
        "- **Hand-picked, not a benchmark.** These runs were chosen to show how the system "
        "behaves, refusals included. Measured accuracy is in [EVAL_RESULTS.md](EVAL_RESULTS.md).",
        "- **Every number in an answer was filled in by code** from the result rows; the model "
        "writes a template with slots, not the figures.",
        f"- Costs are priced from each run's token counts ({PRICES_AS_OF} prices, "
        "`llm/pricing.py`).",
        "- The same runs are on the web app's public *Recorded runs* page.",
        "",
    ]
    if not recorded.runs:
        return "\n".join([*out, "_No runs recorded yet._", ""])

    out += ["| # | Question | Status | Model | Latency | Cost |", "|---|---|---|---|---|---|"]
    for i, r in enumerate(recorded.runs, 1):
        out.append(
            f"| {i} | {_cell(r.question)} | {r.status} | {_model(r)} | "
            f"{_seconds(r.elapsed_ms)} | ${r.usage.cost_usd:.6f} |"
        )
    for i, r in enumerate(recorded.runs, 1):
        u = r.usage
        calls = (
            f"`{r.model}` · {u.llm_calls} model call{'' if u.llm_calls == 1 else 's'} · "
            f"{u.input_tokens + u.cache_read_tokens + u.cache_write_tokens:,} input / "
            f"{u.output_tokens:,} output tokens"
            if u.llm_calls
            else f"no model call (live, `{r.model}` configured)"
        )
        out += [
            "",
            f"## {i}. {r.question}",
            "",
            f"Recorded {r.created_at[:10]} · signed in as {ROLES.get(r.role, r.role)} · "
            f"{LANGS.get(r.lang, r.lang)} · {calls} · {_seconds(r.elapsed_ms)} · "
            f"${u.cost_usd:.6f}",
            "",
        ]
        if r.status == "refused" and r.refusal:
            by = (
                "by the rule-based guard, before any model call"
                if r.refusal.source == "guard"
                else "by the model"
            )
            out += [f"**Refused {by}:** {r.answer or r.refusal.reason}", ""]
            out += [f"- Try instead: {s}" for s in r.suggestions]
        elif r.answer:
            out += [f"**Answer ({r.status}):** {r.answer}", ""]
        for label, items in (("Assumptions", r.assumptions), ("Caveats", r.caveats)):
            if items:
                out += [f"**{label}:**", "", *[f"- {a}" for a in items], ""]
        if r.sql:
            out += ["```sql", r.sql.strip(), "```", ""]
        if r.columns:
            shown = r.rows[:DOC_ROWS]
            out += [f"Showing {len(shown)} of {r.row_count:,} rows.", "", _table(r.columns, shown)]
        if r.repairs:
            out += ["", f"The SQL was repaired {r.repairs} time(s) before it ran."]
    return "\n".join(out).rstrip() + "\n"


def write_docs(recorded: RecordedRuns, path: Path | None = None) -> None:
    (path or DOCS_PATH).write_text(render_markdown(recorded), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Publish recorded live runs (D048).")
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("dump", help="print the live runs in the run store as JSON")
    d.add_argument("--since", type=date.fromisoformat, help="YYYY-MM-DD")
    a = sub.add_parser("add", help="add runs from a dump to data/recorded_runs.json")
    a.add_argument("file", type=Path)
    a.add_argument("--ids", help="comma-separated run ids (default: every run in the file)")
    sub.add_parser("docs", help="regenerate docs/RECORDED_RUNS.md from the data file")
    sub.add_parser("reprice", help="recompute every run's cost at today's prices, then the docs")
    args = p.parse_args(argv)

    if args.command == "dump":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        json.dump(dump(get_settings().admin_conninfo(), args.since), sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 0
    recorded = load()
    if args.command == "add":
        records = json.loads(args.file.read_text(encoding="utf-8"))
        ids = {i.strip() for i in args.ids.split(",") if i.strip()} if args.ids else None
        added = add(recorded, records, ids)
        save(recorded)
        print(f"added {len(added)} run(s); {len(recorded.runs)} recorded in {DATA_PATH.name}")
    if args.command == "reprice":
        recorded.runs = [priced(r) for r in recorded.runs]
        save(recorded)
        print(f"repriced {len(recorded.runs)} run(s) ({PRICES_AS_OF})")
    write_docs(recorded)
    print(f"wrote {DOCS_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
