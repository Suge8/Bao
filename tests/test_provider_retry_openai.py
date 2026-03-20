# ruff: noqa: F403, F405
from __future__ import annotations

from tests._provider_retry_testkit import *


@pytest.mark.smoke
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
            ChatRequest(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o",
                max_tokens=128,
                temperature=0.1,
                on_progress=_on_progress,
            )
        )

    result = asyncio.run(_run())

    assert result.content == "final"
    assert attempts["count"] == 2
    assert chunks == ["partial", PROGRESS_RESET, "final"]


def test_openai_provider_defers_client_construction() -> None:
    provider = OpenAICompatibleProvider(api_key="k", api_base="https://x.com/v1")

    assert provider._client is None


@pytest.mark.smoke
def test_openai_completions_non_retryable_error_returns_without_retry() -> None:
    provider = OpenAICompatibleProvider(api_key="k", api_base="https://x.com/v1")
    attempts = {"count": 0}
    chunks: list[str] = []

    async def _fake_create(**kwargs):
        del kwargs
        attempts["count"] += 1
        raise _ResponseError("unauthorized", 401)

    async def _on_progress(delta: str) -> None:
        chunks.append(delta)

    provider._client = cast(
        Any,
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_fake_create))),
    )

    async def _run() -> LLMResponse:
        return await provider._chat_completions(
            ChatRequest(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o",
                max_tokens=128,
                temperature=0.1,
                on_progress=_on_progress,
            )
        )

    result = asyncio.run(_run())

    assert attempts["count"] == 1
    assert chunks == []
    assert result.finish_reason == "error"
    assert "unauthorized" in (result.content or "")


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
            ChatRequest(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o",
                max_tokens=128,
                temperature=0.1,
            )
        )

    try:
        asyncio.run(_run())
    except asyncio.CancelledError:
        return

    raise AssertionError("CancelledError should propagate")
