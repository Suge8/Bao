"""Base URL normalization helpers for multiple provider families."""

from bao.providers import (
    _normalize_anthropic_api_base,
    _normalize_gemini_api_base,
    _normalize_openai_api_base,
)
from tests._responses_api_shared import *  # noqa: F401,F403


def test_openai_api_base_accepts_full_endpoint_and_normalizes_to_version_base():
    fallback = "https://api.openai.com/v1"
    assert (
        _normalize_openai_api_base("https://proxy.example.com/chat/completions", fallback)
        == "https://proxy.example.com/v1"
    )
    assert (
        _normalize_openai_api_base("https://proxy.example.com/v1/chat/completions", fallback)
        == "https://proxy.example.com/v1"
    )
    assert (
        _normalize_openai_api_base("https://proxy.example.com/v1/responses", fallback)
        == "https://proxy.example.com/v1"
    )
    assert (
        _normalize_openai_api_base("https://proxy.example.com/v1", fallback)
        == "https://proxy.example.com/v1"
    )


def test_anthropic_and_gemini_api_base_auto_completion():
    assert (
        _normalize_anthropic_api_base("https://proxy.example.com/messages")
        == "https://proxy.example.com"
    )
    assert (
        _normalize_anthropic_api_base("https://proxy.example.com/v1/messages")
        == "https://proxy.example.com"
    )
    assert (
        _normalize_anthropic_api_base("https://proxy.example.com/v1") == "https://proxy.example.com"
    )

    assert _normalize_gemini_api_base("https://proxy.example.com/models") == (
        "https://proxy.example.com/v1beta"
    )
    assert _normalize_gemini_api_base("https://proxy.example.com/v1beta/models") == (
        "https://proxy.example.com/v1beta"
    )
    assert _normalize_gemini_api_base("https://proxy.example.com/v1beta") == (
        "https://proxy.example.com/v1beta"
    )
