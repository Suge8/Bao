"""Mode resolution, request body, and base URL normalization for Responses API provider."""

import asyncio
import json

from pydantic import SecretStr

from bao.providers._openai_provider_common import _system_prompt_seems_ignored
from bao.providers.api_mode_cache import get_cached_mode, set_cached_mode
from bao.providers.base import ChatRequest
from bao.providers.openai_provider import OpenAICompatibleProvider
from tests._responses_api_shared import *  # noqa: F401,F403


def test_openai_provider_build_responses_body_forwards_service_tier() -> None:
    provider = OpenAICompatibleProvider(api_key="k", api_base="https://example.com/v1")

    body = provider._build_responses_body(
        ChatRequest(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-5.2",
            max_tokens=256,
            temperature=0.1,
            reasoning_effort="low",
            service_tier="priority",
        )
    )

    assert body["reasoning"] == {"effort": "low"}
    assert body["service_tier"] == "priority"


def test_openai_provider_build_responses_body_maps_reasoning_off_to_none() -> None:
    provider = OpenAICompatibleProvider(api_key="k", api_base="https://example.com/v1")

    body = provider._build_responses_body(
        ChatRequest(
            messages=[{"role": "user", "content": "hi"}],
            model="gpt-5.2",
            max_tokens=256,
            temperature=0.1,
            reasoning_effort="none",
        )
    )

    assert body["reasoning"] == {"effort": "none"}


def test_openai_provider_chat_completions_forwards_service_tier(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(api_key="k", api_base="https://example.com/v1")
    captured: dict[str, object] = {}

    class _Stream:
        def __aiter__(self):
            async def _gen():
                yield type(
                    "Chunk",
                    (),
                    {
                        "choices": [
                            type(
                                "Choice",
                                (),
                                {
                                    "delta": type(
                                        "Delta",
                                        (),
                                        {
                                            "content": None,
                                            "reasoning_content": None,
                                            "tool_calls": None,
                                        },
                                    )(),
                                    "finish_reason": "stop",
                                },
                            )()
                        ],
                        "usage": None,
                    },
                )()

            return _gen()

    class _Completions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _Stream()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(provider, "_get_client", lambda: _Client())

    result = asyncio.run(
        provider._chat_completions(
            ChatRequest(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-5.2",
                max_tokens=256,
                temperature=0.1,
                service_tier="priority",
            )
        )
    )

    assert result.finish_reason == "stop"
    assert captured["service_tier"] == "priority"


def test_openai_provider_chat_completions_maps_reasoning_off_to_none(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(api_key="k", api_base="https://example.com/v1")
    captured: dict[str, object] = {}

    class _Stream:
        def __aiter__(self):
            async def _gen():
                yield type(
                    "Chunk",
                    (),
                    {
                        "choices": [
                            type(
                                "Choice",
                                (),
                                {
                                    "delta": type(
                                        "Delta",
                                        (),
                                        {
                                            "content": None,
                                            "reasoning_content": None,
                                            "tool_calls": None,
                                        },
                                    )(),
                                    "finish_reason": "stop",
                                },
                            )()
                        ],
                        "usage": None,
                    },
                )()

            return _gen()

    class _Completions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _Stream()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(provider, "_get_client", lambda: _Client())

    result = asyncio.run(
        provider.chat(
            ChatRequest(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-5.2",
                reasoning_effort="off",
            )
        )
    )

    assert result.finish_reason == "stop"
    assert captured["reasoning_effort"] == "none"


def test_api_mode_cache(tmp_path):
    import bao.providers.api_mode_cache as cache_mod

    old_cache = cache_mod._cache
    cache_file = tmp_path / "api_mode_cache.json"
    cache_mod._cache = None
    old_cache_file = cache_mod._cache_file
    cache_mod._cache_file = lambda: cache_file
    try:
        if cache_file.exists():
            cache_file.unlink()
        cache_mod._cache = None

        assert get_cached_mode("https://example.com/v1") is None
        set_cached_mode("https://example.com/v1", "responses")
        assert get_cached_mode("https://example.com/v1") == "responses"
        assert get_cached_mode("https://example.com/v1/") == "responses"
        assert get_cached_mode("https://OTHER.com/v1") is None

        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert "https://example.com/v1" in data
        print("✓ api_mode_cache (set/get/persist)")
    finally:
        cache_mod._cache = old_cache
        cache_mod._cache_file = old_cache_file
        cache_file.unlink(missing_ok=True)


def test_provider_resolve_effective_mode(tmp_path):
    import bao.providers.api_mode_cache as cache_mod

    old_cache = cache_mod._cache
    cache_file = tmp_path / "api_mode_resolve.json"
    old_cache_file = cache_mod._cache_file
    cache_mod._cache = None
    cache_mod._cache_file = lambda: cache_file
    try:
        cache_file.unlink(missing_ok=True)
        p = OpenAICompatibleProvider(api_key="k", api_base="https://test.com/v1")
        assert p._resolve_effective_mode() == "auto"
        set_cached_mode("https://test.com/v1", "responses")
        assert p._resolve_effective_mode() == "responses"
        set_cached_mode("https://test.com/v1", "completions")
        assert p._resolve_effective_mode() == "completions"
    finally:
        cache_mod._cache = old_cache
        cache_mod._cache_file = old_cache_file
        cache_file.unlink(missing_ok=True)
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
    print("✓ make_provider uses auto mode detection")


def test_system_prompt_ignored_heuristic_detects_codex_identity() -> None:
    system_prompt = "You are Bao. Respond in 中文."
    assert _system_prompt_seems_ignored(system_prompt, "I am Codex (GPT-5)")


def test_utility_model_uses_same_provider_path(tmp_path):
    import bao.providers.api_mode_cache as cache_mod
    from bao.config.schema import Config, ProviderConfig
    from bao.providers import make_provider

    old_cache = cache_mod._cache
    cache_file = tmp_path / "api_mode_utility.json"
    old_cache_file = cache_mod._cache_file
    cache_mod._cache = None
    cache_mod._cache_file = lambda: cache_file

    try:
        cache_file.unlink(missing_ok=True)
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
        cache_mod._cache_file = old_cache_file
        cache_file.unlink(missing_ok=True)
    print("✓ utility model uses same provider path")
