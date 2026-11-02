"""Model prices in USD per 1M tokens, used to cost every call.

Sources:
- Anthropic list prices (claude-api skill, cached 2026-10-06; checked 2026-10-30).
  Cache writes are the 5-minute TTL rate.
- OpenAI standard-tier prices (developers.openai.com/api/docs/pricing, read 2026-11-02).
  Cache writes use the listed 30-minute write price where the page has one (gpt-6-luna,
  gpt-6.1-terra); it matched the OpenAI dashboard's November bill to the cent (D053). For
  models with no listed write price we assume the normal input rate.
Update this table, with a date, when prices change.
"""

from dataclasses import dataclass

PRICES_AS_OF = "anthropic 2026-10-06, openai 2026-11-02"


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    cache_write: float


PRICES: dict[str, Price] = {
    # Haiku 5.5: prompts <= 100K tokens; above that see LONG_PROMPT_PRICES.
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_read=0.01, cache_write=0.125),
    "claude-sonnet-5-5": Price(input=2.00, output=10.00, cache_read=0.20, cache_write=2.50),
    "claude-opus-5-5": Price(input=4.00, output=20.00, cache_read=0.20, cache_write=5.00),
    # OpenAI (short context, standard tier)
    "gpt-4o-mini": Price(input=0.15, output=0.60, cache_read=0.075, cache_write=0.15),
    "gpt-6-luna": Price(input=0.10, output=0.50, cache_read=0.01, cache_write=0.125),
    "gpt-5-mini": Price(input=0.25, output=2.00, cache_read=0.025, cache_write=0.25),
    "gpt-6.1-terra": Price(input=1.00, output=5.00, cache_read=0.05, cache_write=1.25),
    "fake-keyless": Price(input=0.0, output=0.0, cache_read=0.0, cache_write=0.0),
}
LONG_PROMPT_THRESHOLD = 100_000
LONG_PROMPT_PRICES: dict[str, Price] = {
    "claude-haiku-5-5": Price(input=0.50, output=2.50, cache_read=0.05, cache_write=0.625),
}


class UnknownModelPrice(KeyError):
    pass


def price_for(model: str, prompt_tokens: int = 0) -> Price:
    if prompt_tokens > LONG_PROMPT_THRESHOLD and model in LONG_PROMPT_PRICES:
        return LONG_PROMPT_PRICES[model]
    try:
        return PRICES[model]
    except KeyError:
        raise UnknownModelPrice(f"No price for model {model!r}; add it to llm/pricing.py") from None


def cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    p = price_for(model, input_tokens + cache_read_tokens + cache_write_tokens)
    total = (
        input_tokens * p.input
        + output_tokens * p.output
        + cache_read_tokens * p.cache_read
        + cache_write_tokens * p.cache_write
    )
    return round(total / 1_000_000, 8)
