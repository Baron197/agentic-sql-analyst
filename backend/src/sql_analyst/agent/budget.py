"""Budget guard (safety layer 8): limits per run, checked on every edge of the graph.

When a limit is reached the run goes to `budget_stop` and then `finalize`, which returns
whatever is ready (the result table, if a query ran) with status "partial" and the reason.
The LLM-call limit is checked before entering a node that calls the model, so a run never
makes more calls than allowed; tokens, cost, and time are checked after the fact.
"""

import time

from pydantic import BaseModel

from sql_analyst.config import Settings
from sql_analyst.observability import LLMCall, totals


class BudgetLimits(BaseModel):
    max_llm_calls: int = 8
    max_tokens: int = 60_000
    max_cost_usd: float = 0.05
    max_seconds: float = 60.0
    max_repairs: int = 3  # back to generate_sql after a failed attempt (not a budget stop)

    @classmethod
    def from_settings(cls, s: Settings) -> "BudgetLimits":
        return cls(
            max_llm_calls=s.agent_max_llm_calls,
            max_tokens=s.agent_max_tokens,
            max_cost_usd=s.agent_max_cost_usd,
            max_seconds=s.agent_max_seconds,
            max_repairs=s.agent_max_repairs,
        )

    def exceeded(self, calls: list[LLMCall], started: float, *, next_calls_llm: bool) -> str | None:
        """The reason to stop now, or None."""
        t = totals(calls)
        if next_calls_llm and t.llm_calls >= self.max_llm_calls:
            return f"LLM call limit reached ({self.max_llm_calls} calls)"
        if t.total_tokens > self.max_tokens:
            return f"token limit reached ({self.max_tokens:,} tokens)"
        if t.cost_usd > self.max_cost_usd:
            return f"cost limit reached (${self.max_cost_usd})"
        if time.perf_counter() - started > self.max_seconds:
            return f"time limit reached ({self.max_seconds:g} s)"
        return None
