"""Anthropic adapter: structured outputs via `client.messages.parse`.

Current Claude models reject `temperature`, assistant prefill, and forced tool_choice,
so none are sent. The system prompt (static instructions + dictionary) is marked for
prompt caching; cache reads and writes are recorded and costed.
"""

import time
from typing import Any

import anthropic as sdk

from sql_analyst.llm.base import LLMClient, LLMError, LLMRefusal, Message, T, Usage
from sql_analyst.llm.pricing import cost_usd


class AnthropicLLM(LLMClient):
    provider = "anthropic"

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        effort: str | None = None,
        timeout_s: float = 120.0,
        max_retries: int = 2,
        client: Any = None,
    ):
        self.model = model
        self.effort = effort
        self.client = client or sdk.Anthropic(
            api_key=api_key, timeout=timeout_s, max_retries=max_retries
        )

    def generate_structured(
        self, system: str, messages: list[Message], schema: type[T], *, max_tokens: int = 16_000
    ) -> tuple[T, Usage]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [m.model_dump() for m in messages],
            "output_format": schema,
        }
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        started = time.perf_counter()
        try:
            response = self.client.messages.parse(**kwargs)
        except sdk.APIStatusError as e:
            raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from e
        except sdk.APIConnectionError as e:
            raise LLMError(f"Anthropic API connection error: {e}") from e
        usage = self._usage(response, (time.perf_counter() - started) * 1000)

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise LLMRefusal(f"The model declined the request (category: {category}).", usage)
        if response.stop_reason == "max_tokens":
            raise LLMError(f"The response hit max_tokens={max_tokens} before finishing.", usage)
        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            raise LLMError("The response did not contain a valid structured output.", usage)
        return parsed, usage

    def _usage(self, response: Any, latency_ms: float) -> Usage:
        u = response.usage
        cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0
        model = getattr(response, "model", None) or self.model
        return Usage(
            provider=self.provider,
            model=model,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            cost_usd=cost_usd(model, u.input_tokens, u.output_tokens, cache_read, cache_write),
            latency_ms=round(latency_ms, 1),
        )
