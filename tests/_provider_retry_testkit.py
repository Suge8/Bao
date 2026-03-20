# ruff: noqa: F401
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Self, cast

import pytest

from bao.providers.anthropic_provider import AnthropicProvider
from bao.providers.base import ChatRequest, LLMResponse
from bao.providers.openai_provider import OpenAICompatibleProvider
from bao.providers.retry import (
    PROGRESS_RESET,
    RetryRunOptions,
    compute_retry_delay,
    run_with_retries,
    should_retry_exception,
)

pytestmark = pytest.mark.unit


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


class _AnthropicStreamContext:
    def __init__(self, events: list[Any]):
        self._events = events
        self._index = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> Any:
        if self._index >= len(self._events):
            raise StopAsyncIteration
        event = self._events[self._index]
        self._index += 1
        return event

    async def get_final_message(self) -> Any:
        return SimpleNamespace(
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            stop_reason="end_turn",
            content=[],
        )


__all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]
