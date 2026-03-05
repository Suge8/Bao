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


def _split_path_segments(path: str) -> list[str]:
    return [seg for seg in path.split("/") if seg]


def _trim_suffix_segments(
    path_segments: list[str],
    suffixes: tuple[tuple[str, ...], ...],
) -> list[str]:
    lowered = [seg.lower() for seg in path_segments]
    for suffix in sorted(suffixes, key=len, reverse=True):
        if len(lowered) < len(suffix):
            continue
        if tuple(lowered[-len(suffix) :]) == suffix:
            return path_segments[: -len(suffix)]
    return path_segments


def _normalize_provider_api_base(
    api_base: str | None,
    default_api_base: str | None,
    *,
    endpoint_suffixes: tuple[tuple[str, ...], ...] = (),
) -> str:
    explicit = (api_base or "").strip().rstrip("/")
    fallback = (default_api_base or "").strip().rstrip("/")
    if not explicit:
        return fallback

    explicit_split = urlsplit(explicit)
    explicit_segments = _split_path_segments(explicit_split.path)
    explicit_segments = _trim_suffix_segments(explicit_segments, endpoint_suffixes)

    if not any(_VERSION_SEGMENT_RE.match(seg) for seg in explicit_segments):
        fallback_segments = _trim_suffix_segments(
            _split_path_segments(urlsplit(fallback).path),
            endpoint_suffixes,
        )
        if fallback_segments:
            explicit_segments = [*explicit_segments, *fallback_segments]

    normalized_path = "/" + "/".join(explicit_segments) if explicit_segments else ""
    normalized = SplitResult(
        scheme=explicit_split.scheme,
        netloc=explicit_split.netloc,
        path=normalized_path,
        query="",
        fragment="",
    )
    value = urlunsplit(normalized).rstrip("/")
    return value or explicit


def _normalize_openai_api_base(api_base: str | None, default_api_base: str | None) -> str:
    return _normalize_provider_api_base(
        api_base,
        default_api_base,
        endpoint_suffixes=(("chat", "completions"), ("completions",), ("responses",)),
    )


def _normalize_anthropic_api_base(api_base: str | None) -> str:
    return _normalize_provider_api_base(
        api_base,
        "https://api.anthropic.com/v1/messages",
        endpoint_suffixes=(("messages",),),
    )


def _normalize_gemini_api_base(api_base: str | None) -> str:
    return _normalize_provider_api_base(
        api_base,
        "https://generativelanguage.googleapis.com/v1beta/models",
        endpoint_suffixes=(("models",),),
    )


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
            base_url=_normalize_anthropic_api_base(provider_config.api_base),
        )
    if provider_type == "gemini":
        from bao.providers.gemini_provider import GeminiProvider

        return GeminiProvider(
            api_key=api_key,
            default_model=model,
            base_url=_normalize_gemini_api_base(provider_config.api_base),
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
        model_prefix=model.split("/", 1)[0] if "/" in model else None,
    )
