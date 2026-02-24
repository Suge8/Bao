from bao.providers.registry import find_by_model
from bao.config.schema import Config, ProviderConfig


def test_find_by_model_returns_provider_spec():
    """Test that find_by_model returns correct provider spec."""
    spec = find_by_model("anthropic/claude-opus-4-5")

    assert spec is not None
    assert spec.name == "anthropic"


def test_find_by_model_openai_compatible():
    """Test that openai-compatible models return correct spec."""
    spec = find_by_model("openrouter/anthropic/claude-3.5-sonnet")

    assert spec is not None
    assert spec.provider_type.value == "openai"


def test_anthropic_model_does_not_fallback_to_openai_provider():
    cfg = Config()
    cfg.providers["openai"] = ProviderConfig(type="openai", api_key="test-key")
    assert cfg.get_provider("anthropic/claude-sonnet-4-20250514") is None
