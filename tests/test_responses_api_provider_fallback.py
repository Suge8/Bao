"""Fallback behaviors when Responses API probing fails or returns non-200."""

import asyncio

from bao.providers._openai_provider_responses_chat import _fallback_to_completions
from bao.providers.api_mode_cache import get_cached_mode
from bao.providers.base import ChatRequest, LLMResponse
from bao.providers.openai_provider import OpenAICompatibleProvider
from bao.providers.runtime import ProviderError
from tests._responses_api_shared import *  # noqa: F401,F403


def test_responses_parse_error_falls_back_without_caching_responses(monkeypatch, tmp_path):
    import bao.providers.api_mode_cache as cache_mod

    old_cache = cache_mod._cache
    cache_file = tmp_path / "api_mode_cache.json"
    old_cache_file = cache_mod._cache_file
    cache_mod._cache = None
    cache_mod._cache_file = lambda: cache_file

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
        "bao.providers._openai_provider_responses_chat.httpx.AsyncClient", lambda timeout: _Client()
    )
    monkeypatch.setattr(p, "_chat_completions", _fake_chat)

    try:
        result = asyncio.run(
            p._chat_with_probe(
                ChatRequest(
                    messages=[{"role": "user", "content": "hi"}],
                    model="gpt-4o",
                    max_tokens=256,
                    temperature=0.1,
                )
            )
        )

        assert result.content == "fallback-ok"
        assert get_cached_mode("https://x.com/v1") is None
    finally:
        cache_mod._cache = old_cache
        cache_mod._cache_file = old_cache_file


def test_responses_non_200_falls_back_without_caching_responses(monkeypatch, tmp_path):
    import bao.providers.api_mode_cache as cache_mod

    old_cache = cache_mod._cache
    cache_file = tmp_path / "api_mode_cache.json"
    old_cache_file = cache_mod._cache_file
    cache_mod._cache = None
    cache_mod._cache_file = lambda: cache_file

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
        "bao.providers._openai_provider_responses_chat.httpx.AsyncClient", lambda timeout: _Client()
    )
    monkeypatch.setattr(p, "_chat_completions", _fake_chat)

    try:
        result = asyncio.run(
            p._chat_with_probe(
                ChatRequest(
                    messages=[{"role": "user", "content": "hi"}],
                    model="gpt-4o",
                    max_tokens=256,
                    temperature=0.1,
                )
            )
        )

        assert result.content == "fallback-500"
        assert get_cached_mode("https://y.com/v1") is None
    finally:
        cache_mod._cache = old_cache
        cache_mod._cache_file = old_cache_file


def test_responses_request_fallback_uses_chat_request_signature(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(api_key="k", api_base="https://z.com/v1")
    captured: list[ChatRequest] = []

    async def _fake_chat(request: ChatRequest) -> LLMResponse:
        captured.append(request)
        return LLMResponse(content="fallback-ok", finish_reason="stop")

    monkeypatch.setattr(provider, "_chat_completions", _fake_chat)
    request = ChatRequest(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-4o",
        max_tokens=256,
        temperature=0.1,
    )

    result = asyncio.run(
        _fallback_to_completions(
            provider,
            request,
            ProviderError(
                provider_name="openai",
                code="responses_unsupported",
                message="unsupported",
                fallback_target="completions",
            ),
        )
    )

    assert result.content == "fallback-ok"
    assert captured == [request]
