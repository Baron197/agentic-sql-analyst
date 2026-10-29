"""Build the configured LLM client. Live providers need an API key in `.env`."""

from sql_analyst.config import Settings
from sql_analyst.llm.base import LLMClient
from sql_analyst.llm.fake import FakeLLM, Responder


class LLMNotConfigured(RuntimeError):
    pass


def make_llm(
    provider: str, model: str | None, settings: Settings, fake_responder: Responder | None = None
) -> LLMClient:
    """`provider` is 'fake' (keyless), 'anthropic', or 'openai'. Azure OpenAI comes later (S4)."""
    if provider == "fake":
        if fake_responder is None:
            raise LLMNotConfigured("The fake LLM needs a responder (rule function).")
        return FakeLLM(fake_responder)
    if provider == "anthropic":
        key = settings.anthropic_api_key.get_secret_value()
        if not key:
            raise LLMNotConfigured(
                "ANTHROPIC_API_KEY is not set in .env; live mode is unavailable."
            )
        from sql_analyst.llm.anthropic import AnthropicLLM

        return AnthropicLLM(
            model or settings.llm_model, api_key=key, effort=settings.llm_effort or None
        )
    if provider == "openai":
        key = settings.openai_api_key.get_secret_value()
        if not key:
            raise LLMNotConfigured("OPENAI_API_KEY is not set in .env; live mode is unavailable.")
        from sql_analyst.llm.openai import OpenAILLM

        return OpenAILLM(
            model or settings.llm_model, api_key=key, effort=settings.llm_effort or None
        )
    raise LLMNotConfigured(f"Unknown LLM provider {provider!r}.")


def provider_for_model(model: str) -> str | None:
    """Infer the provider from a model id: claude-* -> anthropic, gpt-*/o<digit>* -> openai."""
    if model.startswith("claude-"):
        return "anthropic"
    if model.startswith("gpt-") or (model[:1] == "o" and model[1:2].isdigit()):
        return "openai"
    return None
