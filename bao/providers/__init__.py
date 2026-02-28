"""LLM provider abstraction module."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import SplitResult, urlsplit, urlunsplit

from bao.providers.base import LLMProvider, LLMResponse
from bao.providers.registry import find_by_model

if TYPE_CHECKING:
    from bao.config.schema import Config
    from bao.providers.anthropic_provider import AnthropicProvider
    from bao.providers.gemini_provider import GeminiProvider
    from bao.providers.openai_codex_provider import OpenAICodexProvider
    from bao.providers.openai_provider import OpenAICompatibleProvider

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "OpenAICodexProvider",
    "OpenAICompatibleProvider",
    "AnthropicProvider",
    "GeminiProvider",
    "make_provider",
]


_VALID_PROVIDER_TYPES = frozenset({"openai", "openai_codex", "anthropic", "gemini"})
_VERSION_SEGMENT_RE = re.compile(r"^v\d+(?:[a-z0-9-]*)?$", re.IGNORECASE)


def _normalize_openai_api_base(api_base: str | None, default_api_base: str | None) -> str:
    explicit = (api_base or "").strip().rstrip("/")
    fallback = (default_api_base or "").strip().rstrip("/")
    if not explicit:
        return fallback

    explicit_split = urlsplit(explicit)
    segments = [seg for seg in explicit_split.path.split("/") if seg]
    if any(_VERSION_SEGMENT_RE.match(seg) for seg in segments):
        return explicit

    fallback_path = urlsplit(fallback).path.rstrip("/")
    if not fallback_path:
        return explicit

    joined_path = f"{explicit_split.path.rstrip('/')}/{fallback_path.lstrip('/')}"
    normalized = SplitResult(
        scheme=explicit_split.scheme,
        netloc=explicit_split.netloc,
        path=joined_path,
        query="",
        fragment="",
    )
    value = urlunsplit(normalized).rstrip("/")
    return value or explicit


def make_provider(config: "Config", model: str | None = None) -> LLMProvider:
    """Create the appropriate LLM provider based on matched provider config's type field."""
    model = model or config.agents.defaults.model
    if not model:
        raise ValueError(
            "未配置模型。请在 config.jsonc 中设置 agents.defaults.model\n"
            "No model configured. Set agents.defaults.model in config.jsonc"
        )
    provider_config = config.get_provider(model)
    if not provider_config:
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
    if provider_type == "openai_codex":
        from bao.providers.openai_codex_provider import OpenAICodexProvider

        return OpenAICodexProvider(default_model=model)

    api_key = provider_config.api_key.get_secret_value()
    if not api_key:
        raise ValueError(
            f"未找到模型 '{model}' 对应的 Provider 或缺少 API Key\n"
            f"No provider with API key found for model '{model}'"
        )

    if provider_type == "anthropic":
        from bao.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=api_key,
            default_model=model,
            base_url=provider_config.api_base,
        )
    if provider_type == "gemini":
        from bao.providers.gemini_provider import GeminiProvider

        return GeminiProvider(
            api_key=api_key,
            default_model=model,
            base_url=provider_config.api_base,
        )
    # openai
    from bao.providers.openai_provider import OpenAICompatibleProvider

    api_base = _normalize_openai_api_base(
        provider_config.api_base,
        spec.default_api_base if spec else "",
    )
    return OpenAICompatibleProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=model,
        extra_headers=provider_config.extra_headers,
        provider_name=spec.name if spec else "openai",
        api_mode=provider_config.api_mode,
        model_prefix=model.split("/", 1)[0] if "/" in model else None,
    )
