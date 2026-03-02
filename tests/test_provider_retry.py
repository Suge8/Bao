import asyncio
from types import SimpleNamespace
from typing import Any, cast

from bao.providers.base import LLMResponse
from bao.providers.openai_provider import OpenAICompatibleProvider
from bao.providers.retry import PROGRESS_RESET, compute_retry_delay, should_retry_exception


class _ResponseError(Exception):
    def __init__(self, message: str, status_code: int, retry_after: str | None = None):
        super().__init__(message)
        headers = {}
        if retry_after is not None:
            headers["retry-after"] = retry_after
        self.response = SimpleNamespace(status_code=status_code, headers=headers)


class _StreamChunk:
    def __init__(self, content: str | None = None, finish_reason: str | None = None):
        delta = SimpleNamespace(content=content, reasoning_content=None, tool_calls=None)
        choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
        self.choices = [choice]


class _FailingStream:
    def __init__(self):
        self._sent_once = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._sent_once:
            self._sent_once = True
            return _StreamChunk(content="partial", finish_reason=None)
        raise RuntimeError("connection reset by peer")


class _SuccessStream:
    def __init__(self):
        self._done = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._done:
            raise StopAsyncIteration
        self._done = True
        return _StreamChunk(content="final", finish_reason="stop")


def test_retry_helper_status_and_retry_after() -> None:
    retryable = _ResponseError("service unavailable", 503)
    non_retryable = _ResponseError("unauthorized", 401)
    retry_after = _ResponseError("rate limit", 429, retry_after="5")

    assert should_retry_exception(retryable)
    assert not should_retry_exception(non_retryable)
    assert compute_retry_delay(retry_after, attempt=0, base_delay=1.0) == 5.0


def test_openai_completions_retry_emits_reset_before_second_attempt() -> None:
    provider = OpenAICompatibleProvider(api_key="k", api_base="https://x.com/v1")

    attempts = {"count": 0}

    async def _fake_create(**kwargs):
        del kwargs
        attempts["count"] += 1
        if attempts["count"] == 1:
            return _FailingStream()
        return _SuccessStream()

    provider._client = cast(
        Any,
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_fake_create))),
    )

    chunks: list[str] = []

    async def _on_progress(delta: str) -> None:
        chunks.append(delta)

    async def _run() -> LLMResponse:
        return await provider._chat_completions(
            "gpt-4o",
            [{"role": "user", "content": "hi"}],
            None,
            128,
            0.1,
            _on_progress,
        )

    result = asyncio.run(_run())

    assert result.content == "final"
    assert attempts["count"] == 2
    assert chunks == ["partial", PROGRESS_RESET, "final"]


def test_openai_completions_cancelled_error_not_swallowed() -> None:
    provider = OpenAICompatibleProvider(api_key="k", api_base="https://x.com/v1")

    async def _raise_cancelled(**kwargs):
        del kwargs
        raise asyncio.CancelledError()

    provider._client = cast(
        Any,
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_raise_cancelled))),
    )

    async def _run() -> LLMResponse:
        return await provider._chat_completions(
            "gpt-4o",
            [{"role": "user", "content": "hi"}],
            None,
            128,
            0.1,
            None,
        )

    try:
        asyncio.run(_run())
    except asyncio.CancelledError:
        return

    raise AssertionError("CancelledError should propagate")


def test_responses_mode_auto_falls_back_to_completions(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(api_key="k", api_base="https://x.com/v1", api_mode="auto")

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

    monkeypatch.setattr(
        "bao.providers.openai_provider.httpx.AsyncClient", lambda timeout: _Client()
    )
    monkeypatch.setattr(provider, "_chat_completions", _fake_chat)

    result = asyncio.run(
        provider._chat_responses(
            "gpt-4o",
            [{"role": "user", "content": "hi"}],
            None,
            256,
            0.1,
        )
    )
    assert result.content == "fallback-ok"


def test_responses_mode_explicit_does_not_fallback(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(
        api_key="k",
        api_base="https://x.com/v1",
        api_mode="responses",
    )

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

    async def _should_not_call(*args, **kwargs):
        del args, kwargs
        raise AssertionError("_chat_completions should not be called in explicit responses mode")

    monkeypatch.setattr(
        "bao.providers.openai_provider.httpx.AsyncClient", lambda timeout: _Client()
    )
    monkeypatch.setattr(provider, "_chat_completions", _should_not_call)

    result = asyncio.run(
        provider._chat_responses(
            "gpt-4o",
            [{"role": "user", "content": "hi"}],
            None,
            256,
            0.1,
        )
    )

    assert result.finish_reason == "error"
    assert "Responses API HTTP 503" in (result.content or "")
