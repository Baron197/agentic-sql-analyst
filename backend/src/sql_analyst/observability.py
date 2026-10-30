"""Run traces (per-node timings, per-call tokens and cost) and the run store.

The CLI stores runs as JSONL under RUNS_DIR (gitignored), one file per day. The API stores
them in Postgres (`app.runs`, api/store.py), written by a separate role so the agent's
database login stays read-only.
"""

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from sql_analyst.llm.base import Usage


class NodeEvent(BaseModel):
    node: str
    ms: float
    note: str | None = None


class LLMCall(BaseModel):
    node: str
    usage: Usage


class UsageTotals(BaseModel):
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    llm_latency_ms: float = 0.0
    keyless: bool = True

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


def totals(calls: Iterable[LLMCall]) -> UsageTotals:
    t = UsageTotals()
    for c in calls:
        u = c.usage
        t.llm_calls += 1
        t.input_tokens += u.input_tokens
        t.output_tokens += u.output_tokens
        t.cache_read_tokens += u.cache_read_tokens
        t.cache_write_tokens += u.cache_write_tokens
        t.cost_usd = round(t.cost_usd + u.cost_usd, 8)
        t.llm_latency_ms = round(t.llm_latency_ms + u.latency_ms, 1)
        t.keyless = t.keyless and u.keyless
    return t


class RunSink(Protocol):
    """Where finalize saves a run: JSONL here (CLI), Postgres in the API (api/store.py)."""

    def save(self, record: dict[str, Any]) -> Any: ...


class RunStore:
    """Append-only JSONL: runs/<YYYY-MM-DD>.jsonl, one JSON object per run."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def save(self, record: dict[str, Any]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{datetime.now().date().isoformat()}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
        return path
