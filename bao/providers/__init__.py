"""LLM provider abstraction module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from bao.providers.base import LLMProvider, LLMResponse
from bao.providers.openai_provider import OpenAICompatibleProvider
from bao.providers.anthropic_provider import AnthropicProvider
from bao.providers.gemini_provider import GeminiProvider
from bao.providers.registry import find_by_model

if TYPE_CHECKING:
    from bao.config.schema import Config

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "OpenAICompatibleProvider",
    "AnthropicProvider",
    "GeminiProvider",
    "make_provider",
]


_VALID_PROVIDER_TYPES = frozenset({"openai", "anthropic", "gemini"})


def make_provider(config: "Config", model: str | None = None) -> LLMProvider:
    """Create the appropriate LLM provider based on matched provider config's type field."""
    model = model or config.agents.defaults.model
    if not model:
        raise ValueError(
            "未配置模型。请在 config.jsonc 中设置 agents.defaults.model\n"
            "No model configured. Set agents.defaults.model in config.jsonc"
        )
    provider_config = config.get_provider(model)
    if not provider_config or not provider_config.api_key:
        raise ValueError(
            f"未找到模型 '{model}' 对应的 Provider 或缺少 API Key\n"
            f"No provider with API key found for model '{model}'"
        )
    provider_type = provider_config.type
    if provider_type not in _VALID_PROVIDER_TYPES:
        raise ValueError(
            f"Provider type '{provider_type}' 无效，是否拼写错误？\n"
            f"有效值 Valid values: {', '.join(sorted(_VALID_PROVIDER_TYPES))}"
        )
    spec = find_by_model(model)
    if provider_type == "anthropic":
        return AnthropicProvider(
            api_key=provider_config.api_key,
            default_model=model,
            base_url=provider_config.api_base,
        )
    if provider_type == "gemini":
        return GeminiProvider(
            api_key=provider_config.api_key,
            default_model=model,
            base_url=provider_config.api_base,
        )
    # openai
    api_base = provider_config.api_base or (spec.default_api_base if spec else "")
    return OpenAICompatibleProvider(
        api_key=provider_config.api_key,
        api_base=api_base,
        default_model=model,
        extra_headers=provider_config.extra_headers,
        provider_name=spec.name if spec else "openai",
        api_mode=provider_config.api_mode,
    )