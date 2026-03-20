# ruff: noqa: F403, F405
from __future__ import annotations

from tests._provider_retry_testkit import *


@pytest.mark.smoke
def test_anthropic_retry_emits_reset_before_second_attempt() -> None:
    provider = AnthropicProvider(api_key="k")
    attempts = {"count": 0}

    def _stream(**kwargs):
        del kwargs
        attempts["count"] += 1
        if attempts["count"] == 1:
            return _AnthropicStreamContext(
                [
                    SimpleNamespace(
                        type="content_block_delta",
                        delta=SimpleNamespace(type="text_delta", text="partial"),
                    )
                ]
            )
        return _AnthropicStreamContext(
            [
                SimpleNamespace(
                    type="content_block_delta",
                    delta=SimpleNamespace(type="text_delta", text="final"),
                )
            ]
        )

    provider._client = cast(Any, SimpleNamespace(messages=SimpleNamespace(stream=_stream)))

    chunks: list[str] = []

    async def _on_progress(delta: str) -> None:
        chunks.append(delta)

    async def _run() -> LLMResponse:
        return await provider.chat(
            ChatRequest(
                messages=[{"role": "user", "content": "hi"}],
                model="claude-sonnet-4-20250514",
                on_progress=_on_progress,
            )
        )

    original_get_final = _AnthropicStreamContext.get_final_message

    async def _failing_get_final(self):
        if attempts["count"] == 1:
            raise RuntimeError("connection reset by peer")
        return await original_get_final(self)

    _AnthropicStreamContext.get_final_message = _failing_get_final
    try:
        result = asyncio.run(_run())
    finally:
        _AnthropicStreamContext.get_final_message = original_get_final

    assert result.content == "final"
    assert attempts["count"] == 2
    assert chunks == ["partial", PROGRESS_RESET, "final"]


def test_anthropic_cancelled_error_not_swallowed() -> None:
    provider = AnthropicProvider(api_key="k")

    class _CancelledStreamContext:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        def __aiter__(self) -> Self:
            return self

        async def __anext__(self) -> Any:
            raise asyncio.CancelledError()

        async def get_final_message(self) -> Any:
            raise AssertionError("should not reach final message")

    provider._client = cast(
        Any,
        SimpleNamespace(
            messages=SimpleNamespace(stream=lambda **kwargs: _CancelledStreamContext())
        ),
    )

    async def _run() -> LLMResponse:
        return await provider.chat(
            ChatRequest(
                messages=[{"role": "user", "content": "hi"}],
                model="claude-sonnet-4-20250514",
            )
        )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_run())
