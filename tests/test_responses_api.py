"""Smoke tests for Responses API auto-detection feature."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import SecretStr

from bao.providers.api_mode_cache import get_cached_mode, set_cached_mode
from bao.providers.base import LLMResponse
from bao.providers.openai_provider import OpenAICompatibleProvider
from bao.providers.responses_compat import (
    convert_messages_to_responses,
    convert_tools_to_responses,
    parse_responses_json,
)


def test_convert_messages_to_responses():
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "function": {"name": "search", "arguments": '{"q": "test"}'}}
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "result"},
    ]
    system_prompt, input_items = convert_messages_to_responses(messages)
    assert system_prompt == "You are helpful.", f"Got: {system_prompt}"
    assert len(input_items) == 4, f"Expected 4 items, got {len(input_items)}"
    assert input_items[0]["role"] == "user"
    assert input_items[1]["type"] == "message"
    assert input_items[1]["role"] == "assistant"
    assert input_items[2]["type"] == "function_call"
    assert input_items[2]["name"] == "search"
    assert input_items[3]["type"] == "function_call_output"
    assert input_items[3]["output"] == "result"
    print("✓ convert_messages_to_responses")


def test_convert_tools_to_responses():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search",
                "parameters": {"type": "object"},
            },
        }
    ]
    result = convert_tools_to_responses(tools)
    assert len(result) == 1
    assert result[0]["type"] == "function"
    assert result[0]["name"] == "search"
    assert "parameters" in result[0]
    print("✓ convert_tools_to_responses")


def test_parse_responses_json():
    data = {
        "status": "completed",
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "Hello!"}]},
            {
                "type": "function_call",
                "call_id": "c1",
                "id": "fc1",
                "name": "tool",
                "arguments": '{"x": 1}',
            },
        ],
        "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
    }
    content, tool_calls, finish_reason, usage = parse_responses_json(data)
    assert content == "Hello!", f"Got: {content}"
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "tool"
    assert tool_calls[0].arguments == {"x": 1}
    assert finish_reason == "stop"
    assert usage["prompt_tokens"] == 10
    assert usage["completion_tokens"] == 20
    print("✓ parse_responses_json")


def test_api_mode_cache(tmp_path):
    import bao.providers.api_mode_cache as cache_mod

    old_cache = cache_mod._cache
    old_file = cache_mod._CACHE_FILE
    cache_mod._cache = None
    cache_mod._CACHE_FILE = tmp_path / "api_mode_cache.json"
    try:
        if cache_mod._CACHE_FILE.exists():
            cache_mod._CACHE_FILE.unlink()
        cache_mod._cache = None

        assert get_cached_mode("https://example.com/v1") is None
        set_cached_mode("https://example.com/v1", "responses")
        assert get_cached_mode("https://example.com/v1") == "responses"
        assert get_cached_mode("https://example.com/v1/") == "responses"
        assert get_cached_mode("https://OTHER.com/v1") is None

        assert cache_mod._CACHE_FILE.exists()
        data = json.loads(cache_mod._CACHE_FILE.read_text())
        assert "https://example.com/v1" in data
        print("✓ api_mode_cache (set/get/persist)")
    finally:
        cache_mod._cache = old_cache
        cache_mod._CACHE_FILE = old_file
        cache_mod._CACHE_FILE.unlink(missing_ok=True)


def test_provider_resolve_effective_mode(tmp_path):
    import bao.providers.api_mode_cache as cache_mod

    old_cache = cache_mod._cache
    old_file = cache_mod._CACHE_FILE
    cache_mod._cache = None
    cache_mod._CACHE_FILE = tmp_path / "api_mode_resolve.json"
    try:
        cache_mod._CACHE_FILE.unlink(missing_ok=True)
        p = OpenAICompatibleProvider(api_key="k", api_base="https://test.com/v1")
        assert p._resolve_effective_mode() == "auto"
        set_cached_mode("https://test.com/v1", "responses")
        assert p._resolve_effective_mode() == "responses"
        set_cached_mode("https://test.com/v1", "completions")
        assert p._resolve_effective_mode() == "completions"
    finally:
        cache_mod._cache = old_cache
        cache_mod._CACHE_FILE = old_file
        cache_mod._CACHE_FILE.unlink(missing_ok=True)
    print("✓ provider _resolve_effective_mode")


def test_make_provider_uses_auto_mode_detection():
    from bao.config.schema import Config, ProviderConfig

    cfg = Config()
    cfg.providers["openai"] = ProviderConfig(type="openai", api_key=SecretStr("test-key"))
    from bao.providers import make_provider

    provider = make_provider(cfg, "openai/gpt-4o")
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider._resolve_effective_mode() == "auto"
    assert not hasattr(provider, "_api_mode")
    print("\u2713 make_provider uses auto mode detection")


def test_utility_model_uses_same_provider_path(tmp_path):
    import bao.providers.api_mode_cache as cache_mod
    from bao.config.schema import Config, ProviderConfig
    from bao.providers import make_provider

    old_cache = cache_mod._cache
    old_file = cache_mod._CACHE_FILE
    cache_mod._cache = None
    cache_mod._CACHE_FILE = tmp_path / "api_mode_utility.json"

    try:
        cache_mod._CACHE_FILE.unlink(missing_ok=True)
        cfg = Config()
        cfg.providers["openai"] = ProviderConfig(
            type="openai",
            api_key=SecretStr("test-key"),
            api_base="https://www.right.codes/codex",
        )
        cfg.agents.defaults.model = "openai/gpt-4o"
        cfg.agents.defaults.utility_model = "openai/gpt-4o-mini"
        utility_provider = make_provider(cfg, cfg.agents.defaults.utility_model)
        assert isinstance(utility_provider, OpenAICompatibleProvider)
        assert utility_provider._resolve_effective_mode() == "auto"
        assert not hasattr(utility_provider, "_api_mode")
        assert utility_provider._effective_base == "https://www.right.codes/codex/v1"
    finally:
        cache_mod._cache = old_cache
        cache_mod._CACHE_FILE = old_file
        cache_mod._CACHE_FILE.unlink(missing_ok=True)
    print("\u2713 utility model uses same provider path")


def test_openai_api_base_accepts_full_endpoint_and_normalizes_to_version_base():
    from bao.providers import _normalize_openai_api_base

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
    from bao.providers import _normalize_anthropic_api_base, _normalize_gemini_api_base

    assert _normalize_anthropic_api_base("https://proxy.example.com/messages") == (
        "https://proxy.example.com/v1"
    )
    assert _normalize_anthropic_api_base("https://proxy.example.com/v1/messages") == (
        "https://proxy.example.com/v1"
    )
    assert _normalize_anthropic_api_base("https://proxy.example.com/v1") == (
        "https://proxy.example.com/v1"
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


def test_responses_parse_error_falls_back_without_caching_responses(monkeypatch, tmp_path):
    import bao.providers.api_mode_cache as cache_mod

    old_cache = cache_mod._cache
    old_file = cache_mod._CACHE_FILE
    cache_mod._cache = None
    cache_mod._CACHE_FILE = tmp_path / "api_mode_cache.json"

    p = OpenAICompatibleProvider(api_key="k", api_base="https://x.com/v1")

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            return _Resp()

    async def _fake_chat(*args, **kwargs):
        return LLMResponse(content="fallback-ok", finish_reason="stop")

    monkeypatch.setattr(
        "bao.providers.openai_provider.httpx.AsyncClient", lambda timeout: _Client()
    )
    monkeypatch.setattr(p, "_chat_completions", _fake_chat)

    try:
        result = asyncio.run(
            p._chat_with_probe("gpt-4o", [{"role": "user", "content": "hi"}], None, 256, 0.1)
        )

        assert result.content == "fallback-ok"
        assert get_cached_mode("https://x.com/v1") is None
    finally:
        cache_mod._cache = old_cache
        cache_mod._CACHE_FILE = old_file


def test_responses_non_200_falls_back_without_caching_responses(monkeypatch, tmp_path):
    import bao.providers.api_mode_cache as cache_mod

    old_cache = cache_mod._cache
    old_file = cache_mod._CACHE_FILE
    cache_mod._cache = None
    cache_mod._CACHE_FILE = tmp_path / "api_mode_cache.json"

    p = OpenAICompatibleProvider(api_key="k", api_base="https://y.com/v1")

    class _Resp:
        status_code = 500
        text = "upstream error"

        def json(self):
            return {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            return _Resp()

    async def _fake_chat(*args, **kwargs):
        return LLMResponse(content="fallback-500", finish_reason="stop")

    monkeypatch.setattr(
        "bao.providers.openai_provider.httpx.AsyncClient", lambda timeout: _Client()
    )
    monkeypatch.setattr(p, "_chat_completions", _fake_chat)

    try:
        result = asyncio.run(
            p._chat_with_probe("gpt-4o", [{"role": "user", "content": "hi"}], None, 256, 0.1)
        )

        assert result.content == "fallback-500"
        assert get_cached_mode("https://y.com/v1") is None
    finally:
        cache_mod._cache = old_cache
        cache_mod._CACHE_FILE = old_file


if __name__ == "__main__":
    test_convert_messages_to_responses()
    test_convert_tools_to_responses()
    test_parse_responses_json()
    test_make_provider_uses_auto_mode_detection()
    print("\n🎉 All tests passed!")
