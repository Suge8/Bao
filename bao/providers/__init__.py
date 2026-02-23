"""LLM provider abstraction module."""

from bao.providers.base import LLMProvider, LLMResponse
from bao.providers.openai_provider import OpenAICompatibleProvider
from bao.providers.anthropic_provider import AnthropicProvider
from bao.providers.gemini_provider import GeminiProvider
from bao.providers.openai_codex_provider import OpenAICodexProvider
from bao.providers.registry import PROVIDERS, ProviderType, find_by_model, find_by_name

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "OpenAICompatibleProvider",
    "AnthropicProvider",
    "GeminiProvider",
    "OpenAICodexProvider",
    "make_provider",
]


def make_provider(config: "Config", model: str | None = None) -> LLMProvider:
    """Create the appropriate LLM provider for a given model.

    Routes based on provider type:
    - openai_codex (OAuth) -> OpenAICodexProvider
    - anthropic/* -> AnthropicProvider (native SDK)
    - gemini/* -> GeminiProvider (native SDK)
    - everything else -> OpenAICompatibleProvider (OpenAI-compatible endpoints)
    """
    model = model or config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    provider_config = config.get_provider(model)

    # OAuth provider
    if provider_name == "openai_codex" or model.startswith("openai-codex/"):
        return OpenAICodexProvider(default_model=model)

    # Find provider spec
    spec = find_by_name(provider_name) or find_by_model(model)
    if not spec:
        raise ValueError(f"Cannot determine provider for model '{model}'")

    # Route to native SDK providers
    provider_type = spec.provider_type

    if provider_type == ProviderType.ANTHROPIC:
        if not provider_config or not provider_config.api_key:
            raise ValueError(f"No API key configured for '{provider_name}'")
        return AnthropicProvider(api_key=provider_config.api_key, default_model=model)

    if provider_type == ProviderType.GEMINI:
        if not provider_config or not provider_config.api_key:
            raise ValueError(f"No API key configured for '{provider_name}'")
        return GeminiProvider(api_key=provider_config.api_key, default_model=model)

    # OpenAI-compatible providers (default)
    api_base = config.get_api_base(model) or spec.default_api_base
    return OpenAICompatibleProvider(
        api_key=provider_config.api_key if provider_config else None,
        api_base=api_base,
        default_model=model,
        extra_headers=provider_config.extra_headers if provider_config else None,
        provider_name=provider_name,
    )
