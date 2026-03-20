# ruff: noqa: F403, F405
from __future__ import annotations

from tests._provider_retry_testkit import *


def test_responses_mode_auto_falls_back_to_completions(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(api_key="k", api_base="https://x.com/v1")

    class _Resp:
        status_code = 503
        text = "upstream unavailable"

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        async def post(self, *args, **kwargs):
            del args, kwargs
            return _Resp()

    async def _fake_chat(*args, **kwargs):
        del args, kwargs
        return LLMResponse(content="fallback-ok", finish_reason="stop")

    monkeypatch.setattr("bao.providers._openai_provider_responses_chat.httpx.AsyncClient", lambda timeout: _Client())
    monkeypatch.setattr(provider, "_chat_completions", _fake_chat)

    result = asyncio.run(
        provider._chat_responses(
            ChatRequest(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o",
                max_tokens=256,
                temperature=0.1,
            )
        )
    )
    assert result.content == "fallback-ok"


def test_responses_mode_fallback_on_http_error(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(api_key="k", api_base="https://x.com/v1")

    class _Resp:
        status_code = 503
        text = "upstream unavailable"

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        async def post(self, *args, **kwargs):
            del args, kwargs
            return _Resp()

    async def _fake_chat(*args, **kwargs):
        del args, kwargs
        return LLMResponse(content="fallback-503", finish_reason="stop")

    monkeypatch.setattr("bao.providers._openai_provider_responses_chat.httpx.AsyncClient", lambda timeout: _Client())
    monkeypatch.setattr(provider, "_chat_completions", _fake_chat)

    result = asyncio.run(
        provider._chat_responses(
            ChatRequest(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o",
                max_tokens=256,
                temperature=0.1,
            )
        )
    )

    assert result.content == "fallback-503"
