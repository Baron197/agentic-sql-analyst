"""Keyless, deterministic stand-in for an LLM. Used by tests, CI, and keyless demo runs.

Its outputs come from a rule function supplied by the caller, cost nothing, and are
labelled `keyless=True` everywhere. Results produced with it test the plumbing, never
model quality.
"""

import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from sql_analyst.llm.base import LLMClient, LLMError, Message, T, Usage

Responder = Callable[[str, list[Message], type[BaseModel]], BaseModel | dict[str, Any]]


class FakeLLM(LLMClient):
    provider = "fake"
    model = "fake-keyless"

    def __init__(self, responder: Responder):
        self.responder = responder

    def generate_structured(
        self, system: str, messages: list[Message], schema: type[T], *, max_tokens: int = 16_000
    ) -> tuple[T, Usage]:
        started = time.perf_counter()
        raw = self.responder(system, messages, schema)
        try:
            parsed = raw if isinstance(raw, schema) else schema.model_validate(raw)
        except Exception as e:  # a broken rule is a test bug: surface it as an LLM error
            raise LLMError(f"Fake responder returned invalid {schema.__name__}: {e}") from e
        usage = Usage(
            provider=self.provider,
            model=self.model,
            input_tokens=(len(system) + sum(len(m.content) for m in messages)) // 4,
            output_tokens=len(parsed.model_dump_json()) // 4,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            keyless=True,
        )
        return parsed, usage
