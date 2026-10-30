"""Command-line entry point.

    uv run poe ask "How many orders were placed each month in 2025?"
    uv run poe ask "Berapa pelanggan baru ..." --user manager_jakarta
    uv run poe ask "..." --mode live --model gpt-6-luna     # paid API call: needs a key

Keyless mode (the default) answers the demo questions in data/demo.yaml with a rule-based
stand-in for the model; everything else in the pipeline runs for real.
"""

import argparse
import json
import sys
from typing import Any

import sqlglot

from sql_analyst.agent.budget import BudgetLimits
from sql_analyst.agent.deps import AgentConfig
from sql_analyst.agent.factory import build_agent
from sql_analyst.agent.keyless import load_demo
from sql_analyst.agent.nodes.finalize import AgentResult
from sql_analyst.config import get_settings
from sql_analyst.dictionary.loader import load_dictionary
from sql_analyst.llm.factory import provider_for_model
from sql_analyst.safety.executor import Executor
from sql_analyst.users import DEMO_USERS

TABLE_ROWS = 15
CELL_WIDTH = 32


def _cell(v: Any) -> str:
    s = "NULL" if v is None else str(v)
    return s if len(s) <= CELL_WIDTH else s[: CELL_WIDTH - 1] + "…"


def _table(r: AgentResult) -> list[str]:
    rows = [[_cell(v) for v in row] for row in r.rows[:TABLE_ROWS]]
    widths = [max([len(c)] + [len(row[j]) for row in rows]) for j, c in enumerate(r.columns)]
    line = " | ".join(c.ljust(w) for c, w in zip(r.columns, widths, strict=True))
    out = ["  " + line, "  " + "-+-".join("-" * w for w in widths)]
    out += ["  " + " | ".join(v.ljust(w) for v, w in zip(row, widths, strict=True)) for row in rows]
    if r.row_count > TABLE_ROWS:
        out.append(f"  ... {r.row_count - TABLE_ROWS} more rows")
    return out


def print_result(r: AgentResult) -> None:
    mode = "keyless (rule-based stand-in, not a model)" if r.usage.keyless else f"live ({r.model})"
    print(f"PT Arunika Niaga: fictional, synthetic data | mode: {mode} | user: {r.user_id}")
    print(f"Status: {r.status}" + (f" ({r.stop_reason})" if r.stop_reason else ""))
    print(f"\n{r.answer}")
    if r.refusal:
        print(f"  reason ({r.refusal.source}): {r.refusal.reason}")
    if r.error:
        print(f"  error: {r.error}")
    if r.assumptions:
        print("\nAssumptions:")
        print("\n".join(f"  - {a}" for a in r.assumptions))
    if r.caveats:
        print("\nCaveats:")
        print("\n".join(f"  - {c}" for c in r.caveats))
    if r.sql:
        print("\nSQL (validated, run as the read-only role with your region scope):")
        pretty = sqlglot.transpile(r.sql, read="postgres", write="postgres", pretty=True)[0]
        print("\n".join("  " + line for line in pretty.splitlines()))
    if r.columns:
        print(f"\nResult: {r.row_count} rows" + (" (truncated)" if r.truncated else ""))
        print("\n".join(_table(r)))
    if r.chart and r.chart.type != "table":
        print(f"\nChart: {r.chart.type} (x={r.chart.x}, y={r.chart.y})")
    print("\nTrace:")
    for e in r.trace:
        print(f"  {e.node:<17} {e.ms:>8.1f} ms  {e.note or ''}")
    u = r.usage
    print(
        f"Usage: {u.llm_calls} LLM calls, {u.input_tokens + u.cache_read_tokens + u.cache_write_tokens:,} "
        f"input tokens ({u.cache_read_tokens:,} cached), {u.output_tokens:,} output, "
        f"${u.cost_usd:.6f}; repairs {r.repairs}; total {r.elapsed_ms:,.0f} ms; run {r.run_id}"
    )


def ask(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="sql-analyst ask", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    p.add_argument("question", nargs="?", help="omit to list the keyless demo questions")
    p.add_argument("--user", choices=sorted(DEMO_USERS), default="analyst")
    p.add_argument("--mode", choices=["keyless", "live"], default="keyless")
    p.add_argument("--model", default=None, help="live model id (default: LLM_MODEL)")
    p.add_argument("--provider", choices=["openai", "anthropic"], default=None)
    p.add_argument("--critic", action="store_true", help="turn on the optional critic call")
    p.add_argument("--json", action="store_true", help="print the full result as JSON")
    p.add_argument("--no-store", action="store_true", help="do not save the run under RUNS_DIR")
    args = p.parse_args(argv)

    if not args.question:
        print("Keyless demo questions (data/demo.yaml):")
        for d in load_demo():
            print(f"  [{d.lang}] {d.question}")
        return 0

    settings = get_settings()
    provider = "fake"
    if args.mode == "live":
        provider = (
            args.provider
            or (args.model and provider_for_model(args.model))
            or settings.llm_provider
        )
        if provider == "fake":
            print("Live mode needs a provider: pass --model or --provider.", file=sys.stderr)
            return 2
    config = AgentConfig(limits=BudgetLimits.from_settings(settings), critic=args.critic)
    with Executor.from_settings(settings, load_dictionary()) as executor:
        agent = build_agent(
            settings,
            executor,
            provider=provider,
            model=args.model,
            config=config,
            store_runs=not args.no_store,
        )
        result = agent.ask(args.question, DEMO_USERS[args.user])
    if args.json:
        print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
    else:
        print_result(result)
    return 0 if result.status in ("answered", "refused") else 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("ask",):
        print("usage: sql-analyst ask [question] [--user ...] [--mode keyless|live]")
        return 2
    return ask(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
