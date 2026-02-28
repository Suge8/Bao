"""
Provider Registry — simplified routing for OpenAI-compatible, Anthropic, and Gemini providers.

This replaces the litellm-based provider system with native SDK support.
No longer needs complex prefix/keyword matching — just 3 provider types.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProviderType(Enum):
    """Provider type enumeration - only 3 types now."""

    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


@dataclass(frozen=True)
class ProviderSpec:
    """One LLM provider's metadata."""

    # identity
    name: str  # config field name, e.g. "openai", "anthropic", "gemini"
    provider_type: ProviderType
    keywords: tuple[str, ...]  # model-name keywords for matching (lowercase)
    display_name: str = ""  # human-readable name for display

    # default api_base for OpenAI-compatible providers
    default_api_base: str = ""

    # Does this provider support prompt caching?
    supports_prompt_caching: bool = False


# Simplified provider registry — only what's needed now
PROVIDERS: tuple[ProviderSpec, ...] = (
    # === Anthropic (native SDK) ===
    ProviderSpec(
        name="anthropic",
        provider_type=ProviderType.ANTHROPIC,
        keywords=("anthropic", "claude"),
        display_name="Anthropic",
        supports_prompt_caching=True,
    ),
    # === Gemini (native SDK) ===
    ProviderSpec(
        name="gemini",
        provider_type=ProviderType.GEMINI,
        keywords=("gemini",),
        display_name="Gemini",
    ),
    # === OpenAI-Compatible Providers (default, catch-all) ===
    # These all use the OpenAI-compatible provider with different api_base
    ProviderSpec(
        name="openai",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        keywords=("openai", "gpt"),
        display_name="OpenAI",
        default_api_base="https://api.openai.com/v1",
        supports_prompt_caching=True,
    ),
    ProviderSpec(
        name="openrouter",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        keywords=("openrouter",),
        display_name="OpenRouter",
        default_api_base="https://openrouter.ai/api/v1",
        supports_prompt_caching=True,
    ),
    ProviderSpec(
        name="deepseek",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        keywords=("deepseek",),
        display_name="DeepSeek",
        default_api_base="https://api.deepseek.com/v1",
    ),
    ProviderSpec(
        name="groq",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        keywords=("groq",),
        display_name="Groq",
        default_api_base="https://api.groq.com/openai/v1",
    ),
    ProviderSpec(
        name="siliconflow",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        keywords=("siliconflow",),
        display_name="SiliconFlow",
        default_api_base="https://api.siliconflow.cn/v1",
    ),
    ProviderSpec(
        name="volcengine",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        keywords=("volcengine", "volces", "ark"),
        display_name="VolcEngine",
        default_api_base="https://ark.cn-beijing.volces.com/api/v3",
    ),
    ProviderSpec(
        name="dashscope",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        keywords=("qwen", "dashscope"),
        display_name="DashScope",
        default_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    ProviderSpec(
        name="moonshot",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        keywords=("moonshot", "kimi"),
        display_name="Moonshot",
        default_api_base="https://api.moonshot.ai/v1",
    ),
    ProviderSpec(
        name="minimax",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        keywords=("minimax",),
        display_name="MiniMax",
        default_api_base="https://api.minimax.io/v1",
    ),
    ProviderSpec(
        name="zhipu",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        keywords=("zhipu", "glm", "zai"),
        display_name="Zhipu AI",
        default_api_base="https://open.bigmodel.cn/api/paas/v4",
    ),
    ProviderSpec(
        name="vllm",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        keywords=("vllm",),
        display_name="vLLM/Local",
        default_api_base="http://localhost:8000/v1",
    ),
    ProviderSpec(
        name="ollama",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        keywords=("ollama",),
        display_name="Ollama",
        default_api_base="http://localhost:11434/v1",
    ),
    ProviderSpec(
        name="lmstudio",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        keywords=("lmstudio", "lm-studio"),
        display_name="LM Studio",
        default_api_base="http://localhost:1234/v1",
    ),
    ProviderSpec(
        name="aihubmix",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        keywords=("aihubmix",),
        display_name="AiHubMix",
        default_api_base="https://aihubmix.com/v1",
    ),
)


def find_by_model(model: str) -> ProviderSpec | None:
    """Match a provider by model name (prefix or keyword)."""
    model_lower = model.lower()
    model_prefix = model_lower.split("/", 1)[0] if "/" in model_lower else ""
    normalized_prefix = model_prefix.replace("-", "_")

    # First: try exact prefix match
    for spec in PROVIDERS:
        if normalized_prefix == spec.name:
            return spec

    # Second: try keyword match
    for spec in PROVIDERS:
        for kw in spec.keywords:
            if kw in model_lower or kw.replace("-", "_") in model_lower:
                return spec

    # Default: return OpenAI as fallback for unknown models
    return next(s for s in PROVIDERS if s.name == "openai")


def find_by_name(name: str) -> ProviderSpec | None:
    """Find a provider spec by config field name."""
    normalized = name.lower().replace("-", "_")
    for spec in PROVIDERS:
        if spec.name == normalized:
            return spec
    return None


def get_provider_type(model: str) -> ProviderType:
    """Get the provider type for a given model."""
    spec = find_by_model(model)
    return spec.provider_type if spec else ProviderType.OPENAI_COMPATIBLE


def get_default_api_base(provider_name: str) -> str:
    """Get default API base URL for a provider."""
    spec = find_by_name(provider_name)
    return spec.default_api_base if spec else ""
