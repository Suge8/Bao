from bao.providers.openai_codex_provider import _strip_model_prefix
from bao.providers.registry import find_by_model


def test_find_by_model_returns_provider_spec():
    """Test that find_by_model returns correct provider spec."""
    spec = find_by_model("anthropic/claude-opus-4-5")

    assert spec is not None
    assert spec.name == "anthropic"


def test_find_by_model_openai_compatible():
    """Test that openai-compatible models return correct spec."""
    spec = find_by_model("openrouter/anthropic/claude-3.5-sonnet")

    assert spec is not None
    assert spec.provider_type.value == "openai_compatible"


def test_openai_codex_strip_prefix_supports_hyphen_and_underscore():
    assert _strip_model_prefix("openai-codex/gpt-5.1-codex") == "gpt-5.1-codex"
    assert _strip_model_prefix("openai_codex/gpt-5.1-codex") == "gpt-5.1-codex"
