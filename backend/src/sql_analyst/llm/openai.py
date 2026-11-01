"""OpenAI adapter: structured outputs via the Responses API (`client.responses.parse`).

The system prompt goes in `instructions`; OpenAI caches long identical prefixes
automatically. Each call also sends `prompt_cache_key`, derived from the system prompt, so
calls that share a prompt are routed to the same cache: without it the agent's SQL prompt
was rewritten to the cache on most questions (docs/DECISIONS.md D041). `input_tokens`
from the API includes cached tokens, so the uncached part is input_tokens - cached_tokens.
Responses are not stored (`store=False`).
"""

import hashlib
import time
from typing import Any

import openai as sdk

from sql_analyst.llm.base import LLMClient, LLMError, LLMRefusal, Message, T, Usage
from sql_analyst.llm.pricing import cost_usd


class OpenAILLM(LLMClient):
    provider = "openai"

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
        self.client = client or sdk.OpenAI(
            api_key=api_key, timeout=timeout_s, max_retries=max_retries
        )

    def generate_structured(
        self, system: str, messages: list[Message], schema: type[T], *, max_tokens: int = 16_000
    ) -> tuple[T, Usage]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "instructions": system,
            "input": [m.model_dump() for m in messages],
            "text_format": schema,
            "max_output_tokens": max_tokens,
            "store": False,
            "prompt_cache_key": cache_key(system),
        }
        if self.effort:  # reasoning models only
            kwargs["reasoning"] = {"effort": self.effort}
        started = time.perf_counter()
        try:
            response = self.client.responses.parse(**kwargs)
        except sdk.APIStatusError as e:
            raise LLMError(f"OpenAI API error {e.status_code}: {e.message}") from e
        except sdk.APIConnectionError as e:
            raise LLMError(f"OpenAI API connection error: {e}") from e
        usage = self._usage(response, (time.perf_counter() - started) * 1000)

        if getattr(response, "status", None) == "incomplete":
            reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
            raise LLMError(f"The response is incomplete ({reason}).", usage)
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            if _refusal_text(response):
                raise LLMRefusal(
                    f"The model declined the request: {_refusal_text(response)[:200]}", usage
                )
            raise LLMError("The response did not contain a valid structured output.", usage)
        return parsed, usage

    def _usage(self, response: Any, latency_ms: float) -> Usage:
        u = response.usage
        details = getattr(u, "input_tokens_details", None)
        cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
        written = (getattr(details, "cache_write_tokens", 0) or 0) if details else 0
        uncached = max(0, u.input_tokens - cached - written)
        model = self.model  # bill by the requested id: response.model may carry a dated suffix
        return Usage(
            provider=self.provider,
            model=model,
            input_tokens=uncached,
            output_tokens=u.output_tokens,  # includes reasoning tokens
            cache_read_tokens=cached,
            cache_write_tokens=written,
            cost_usd=cost_usd(model, uncached, u.output_tokens, cached, written),
            latency_ms=round(latency_ms, 1),
        )


def cache_key(system: str) -> str:
    """Stable per system prompt: same prompt, same key (no user data in it)."""
    return "sqla-" + hashlib.sha256(system.encode("utf-8")).hexdigest()[:16]


def _refusal_text(response: Any) -> str:
    for item in getattr(response, "output", None) or []:
        for part in getattr(item, "content", None) or []:
            if getattr(part, "type", None) == "refusal":
                return getattr(part, "refusal", "") or "refused"
    return ""
