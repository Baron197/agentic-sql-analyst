"""LLM interface, pricing, the fake, and the Anthropic adapter against a stub client (no network)."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from sql_analyst.llm.anthropic import AnthropicLLM
from sql_analyst.llm.base import LLMError, LLMRefusal, Message
from sql_analyst.llm.fake import FakeLLM
from sql_analyst.llm.pricing import UnknownModelPrice, cost_usd


class Out(BaseModel):
    answer: str


def test_cost_uses_per_million_prices_including_cache():
    # Haiku 5.5: $0.10 in, $0.50 out, $0.01 cache read, $0.125 cache write per 1M tokens.
    # (Prompts over 100K tokens use Haiku's long-prompt rate card; see the next test.)
    assert cost_usd("claude-haiku-5-5", 100_000, 0) == pytest.approx(0.01)
    assert cost_usd("claude-haiku-5-5", 0, 1_000_000) == pytest.approx(0.50)
    assert cost_usd("claude-haiku-5-5", 10_000, 0, cache_read_tokens=90_000) == pytest.approx(
        0.0019
    )
    assert cost_usd("claude-sonnet-5-5", 15_000, 2_000) == pytest.approx(0.05)


def test_haiku_long_prompts_use_the_higher_rate_card():
    assert cost_usd("claude-haiku-5-5", 200_000, 0) == pytest.approx(0.10)  # $0.50 per 1M


def test_unknown_model_has_no_silent_zero_price():
    with pytest.raises(UnknownModelPrice):
        cost_usd("some-new-model", 10, 10)


def test_fake_llm_is_free_and_labelled_keyless():
    llm = FakeLLM(lambda system, messages, schema: {"answer": "ok"})
    out, usage = llm.generate_structured("sys", [Message(role="user", content="hi")], Out)
    assert out.answer == "ok"
    assert usage.keyless and usage.cost_usd == 0 and usage.model == "fake-keyless"


def test_fake_llm_rejects_invalid_output():
    llm = FakeLLM(lambda *_: {"wrong": 1})
    with pytest.raises(LLMError):
        llm.generate_structured("sys", [], Out)


class _StubMessages:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def _response(stop_reason="end_turn", parsed=None, **usage):
    u = {
        "input_tokens": 1000,
        "output_tokens": 200,
        "cache_read_input_tokens": 9000,
        "cache_creation_input_tokens": 0,
    }
    u.update(usage)
    return SimpleNamespace(
        stop_reason=stop_reason, parsed_output=parsed, model="claude-haiku-5-5",
        usage=SimpleNamespace(**u), stop_details=SimpleNamespace(category="cyber"),
    )  # fmt: skip


def _llm(response):
    stub = _StubMessages(response)
    return AnthropicLLM("claude-haiku-5-5", client=SimpleNamespace(messages=stub)), stub


def test_adapter_sends_structured_output_and_cached_system_prompt_only():
    llm, stub = _llm(_response(parsed=Out(answer="hi")))
    out, usage = llm.generate_structured(
        "SYSTEM", [Message(role="user", content="q")], Out, max_tokens=500
    )
    assert out.answer == "hi"
    assert stub.kwargs["output_format"] is Out
    assert stub.kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert not {"temperature", "top_p", "top_k", "tool_choice"} & set(stub.kwargs)
    assert stub.kwargs["messages"][-1]["role"] == "user"  # no assistant prefill
    assert usage.cache_read_tokens == 9000
    expected = (1000 * 0.10 + 200 * 0.50 + 9000 * 0.01) / 1_000_000
    assert usage.cost_usd == pytest.approx(expected)


def test_adapter_raises_on_refusal_and_keeps_the_usage():
    llm, _ = _llm(_response(stop_reason="refusal"))
    with pytest.raises(LLMRefusal) as info:
        llm.generate_structured("s", [Message(role="user", content="q")], Out)
    assert info.value.usage is not None and info.value.usage.output_tokens == 200


def test_adapter_raises_when_output_is_cut_off():
    llm, _ = _llm(_response(stop_reason="max_tokens"))
    with pytest.raises(LLMError):
        llm.generate_structured("s", [Message(role="user", content="q")], Out)


# ------------------------------------------------------------------ OpenAI
class _StubResponses:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def _openai_response(status="completed", parsed=None, output=(), input_tokens=10_000, cached=8_000):
    usage = SimpleNamespace(
        input_tokens=input_tokens,  # OpenAI: includes the cached tokens
        input_tokens_details=SimpleNamespace(cached_tokens=cached, cache_write_tokens=0),
        output_tokens=300,
        output_tokens_details=SimpleNamespace(reasoning_tokens=0),
    )
    return SimpleNamespace(
        status=status, output_parsed=parsed, output=list(output), usage=usage,
        incomplete_details=SimpleNamespace(reason="max_output_tokens"), model="gpt-4o-mini-2024-07-18",
    )  # fmt: skip


def _openai_llm(response):
    from sql_analyst.llm.openai import OpenAILLM

    stub = _StubResponses(response)
    return OpenAILLM("gpt-4o-mini", client=SimpleNamespace(responses=stub)), stub


def test_openai_adapter_uses_structured_outputs_and_subtracts_cached_tokens():
    llm, stub = _openai_llm(_openai_response(parsed=Out(answer="hi")))
    out, usage = llm.generate_structured(
        "SYSTEM", [Message(role="user", content="q")], Out, max_tokens=500
    )
    assert out.answer == "hi"
    assert stub.kwargs["text_format"] is Out and stub.kwargs["instructions"] == "SYSTEM"
    assert stub.kwargs["store"] is False
    assert not {"temperature", "top_p", "tool_choice"} & set(stub.kwargs)
    # Same system prompt -> same cache key; a different prompt -> a different one.
    key = stub.kwargs["prompt_cache_key"]
    llm.generate_structured("SYSTEM", [Message(role="user", content="other q")], Out)
    assert stub.kwargs["prompt_cache_key"] == key and key.startswith("sqla-")
    llm.generate_structured("ANOTHER", [Message(role="user", content="q")], Out)
    assert stub.kwargs["prompt_cache_key"] != key
    assert (usage.input_tokens, usage.cache_read_tokens, usage.output_tokens) == (2_000, 8_000, 300)
    assert usage.model == "gpt-4o-mini"  # billed by the requested id, not the dated snapshot
    expected = (2_000 * 0.15 + 8_000 * 0.075 + 300 * 0.60) / 1_000_000
    assert usage.cost_usd == pytest.approx(expected)


def test_openai_adapter_raises_on_incomplete_and_refusal():
    llm, _ = _openai_llm(_openai_response(status="incomplete"))
    with pytest.raises(LLMError):
        llm.generate_structured("s", [Message(role="user", content="q")], Out)
    refusal = SimpleNamespace(
        content=[SimpleNamespace(type="refusal", refusal="I can't help with that.")]
    )
    llm, _ = _openai_llm(_openai_response(output=[refusal]))
    with pytest.raises(LLMRefusal) as info:
        llm.generate_structured("s", [Message(role="user", content="q")], Out)
    assert info.value.usage is not None


def test_provider_is_inferred_from_the_model_id():
    from sql_analyst.llm.factory import provider_for_model

    assert provider_for_model("claude-haiku-5-5") == "anthropic"
    assert provider_for_model("gpt-4o-mini") == "openai"
    assert provider_for_model("o4-mini") == "openai"
    assert provider_for_model("mystery") is None
