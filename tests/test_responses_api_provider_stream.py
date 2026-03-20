"""Streaming behaviors for Responses API paths."""

import asyncio

import httpx

from bao.providers.base import ChatRequest
from bao.providers.openai_provider import OpenAICompatibleProvider
from tests._responses_api_shared import *  # noqa: F401,F403


def test_openai_provider_stream_normalizes_internal_tool_call_id(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(api_key="k", api_base="https://example.com/v1")
    raw_call_id = "call_" + ("s" * 90)

    async def _fake_iter_sse_events(_response: httpx.Response):
        yield {
            "type": "response.output_item.added",
            "item": {
                "type": "function_call",
                "call_id": raw_call_id,
                "id": "fc_stream",
                "name": "search",
                "arguments": "{}",
            },
        }
        yield {
            "type": "response.output_item.done",
            "item": {
                "type": "function_call",
                "call_id": raw_call_id,
                "id": "fc_stream",
                "name": "search",
                "arguments": "{}",
            },
        }
        yield {"type": "response.completed", "response": {"status": "completed"}}

    monkeypatch.setattr(provider, "_iter_sse_events", _fake_iter_sse_events)

    response = asyncio.run(
        provider._consume_responses_stream(httpx.Response(200), on_progress=None)
    )

    assert response.finish_reason == "stop"
    assert len(response.tool_calls) == 1
    call_id, item_id = response.tool_calls[0].id.split("|", 1)
    assert item_id == "fc_stream"
    assert len(call_id) <= 64


def test_chat_responses_streams_output_deltas(monkeypatch):
    p = OpenAICompatibleProvider(api_key="k", api_base="https://z.com/v1")
    emitted: list[str] = []

    class _Resp:
        status_code = 200

        async def aiter_lines(self):
            lines = [
                'data: {"type":"response.output_text.delta","delta":"Hello"}',
                "",
                'data: {"type":"response.output_text.delta","delta":" world"}',
                "",
                (
                    'data: {"type":"response.completed","response":{"status":"completed",'
                    '"usage":{"input_tokens":1,"output_tokens":2,"total_tokens":3}}}'
                ),
                "",
                "data: [DONE]",
                "",
            ]
            for line in lines:
                yield line

    class _StreamCtx:
        async def __aenter__(self):
            return _Resp()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *args, **kwargs):
            return _StreamCtx()

    monkeypatch.setattr(
        "bao.providers._openai_provider_responses_chat.httpx.AsyncClient", lambda timeout: _Client()
    )

    async def _on_progress(chunk: str) -> None:
        emitted.append(chunk)

    result = asyncio.run(
        p._chat_responses(
            ChatRequest(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o",
                max_tokens=256,
                temperature=0.1,
                on_progress=_on_progress,
            )
        )
    )

    assert result.content == "Hello world"
    assert result.finish_reason == "stop"
    assert result.usage == {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}
    assert emitted == ["\x00", "Hello", " world"]


def test_chat_responses_stream_without_trailing_blank(monkeypatch):
    p = OpenAICompatibleProvider(api_key="k", api_base="https://z.com/v1")
    emitted: list[str] = []

    class _Resp:
        status_code = 200

        async def aiter_lines(self):
            lines = [
                'data: {"type":"response.output_text.delta","delta":"Hello"}',
                "",
                (
                    'data: {"type":"response.completed","response":{"status":"completed",'
                    '"usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}}}'
                ),
            ]
            for line in lines:
                yield line

    class _StreamCtx:
        async def __aenter__(self):
            return _Resp()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *args, **kwargs):
            return _StreamCtx()

    monkeypatch.setattr(
        "bao.providers._openai_provider_responses_chat.httpx.AsyncClient", lambda timeout: _Client()
    )

    async def _on_progress(chunk: str) -> None:
        emitted.append(chunk)

    result = asyncio.run(
        p._chat_responses(
            ChatRequest(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o",
                max_tokens=256,
                temperature=0.1,
                on_progress=_on_progress,
            )
        )
    )

    assert result.content == "Hello"
    assert result.finish_reason == "stop"
    assert result.usage == {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    assert emitted == ["\x00", "Hello"]

