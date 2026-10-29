"""Provider-agnostic LLM interface. Every model call in the project goes through this.

A call takes a system prompt, messages, and a Pydantic schema, and returns the parsed
object plus a `Usage` record (tokens, cache, cost, latency) for tracing.
"""

from abc import ABC, abstractmethod
from typing import Literal, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class Usage(BaseModel):
    """Tokens, cost, and latency of one LLM call."""

    provider: str
    model: str
    input_tokens: int = 0  # uncached input
    output_tokens: int = 0  # includes thinking tokens
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    keyless: bool = False

    @property
    def total_input_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


class LLMError(Exception):
    """An LLM call failed or returned nothing usable. `usage` is set when tokens were spent."""

    def __init__(self, message: str, usage: Usage | None = None):
        super().__init__(message)
        self.usage = usage


class LLMRefusal(LLMError):
    """The provider declined the request (e.g. a safety classifier)."""


class LLMClient(ABC):
    provider: str
    model: str

    @abstractmethod
    def generate_structured(
        self,
        system: str,
        messages: list[Message],
        schema: type[T],
        *,
        max_tokens: int = 16_000,
    ) -> tuple[T, Usage]:
        """Return an instance of `schema` and the call's usage. Raise LLMError on failure."""
