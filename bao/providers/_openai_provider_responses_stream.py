from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from bao.providers.base import LLMResponse, ToolCallRequest
from bao.providers.responses_compat import (
    append_responses_tool_call_arguments,
    build_responses_tool_call_request,
    parse_responses_json,
    replace_responses_tool_call_arguments,
    start_responses_tool_call,
)
from bao.providers.retry import emit_progress


@dataclass(slots=True)
class _ResponsesStreamState:
    content: str = ""
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    tool_call_buffers: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class _ResponsesEventContext:
    provider: Any
    on_progress: Any


def build_responses_result(payload: dict[str, Any]) -> LLMResponse:
    content, tool_calls, finish_reason, usage = parse_responses_json(payload)
    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        usage=usage,
    )


def decode_responses_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    latest_response = _latest_response_event(response.text or "")
    if latest_response is None:
        raise ValueError("Cannot decode Responses payload")
    return latest_response


def _latest_response_event(text: str) -> dict[str, Any] | None:
    latest_response: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        event = _decode_sse_json(data)
        if not event:
            continue
        response = event.get("response")
        if isinstance(response, dict):
            latest_response = response
            if event.get("type") == "response.completed":
                break
        elif event.get("object") == "response":
            latest_response = event
    return latest_response


def _decode_sse_json(data: str) -> dict[str, Any] | None:
    try:
        event = json.loads(data)
    except Exception:
        return None
    return event if isinstance(event, dict) else None


async def iter_sse_events(response: httpx.Response):
    buffer: list[str] = []
    async for line in response.aiter_lines():
        if line == "":
            event = _parse_sse_buffer(buffer)
            buffer = []
            if event is not None:
                yield event
            continue
        buffer.append(line)
    event = _parse_sse_buffer(buffer)
    if event is not None:
        yield event


def _parse_sse_buffer(lines: list[str]) -> dict[str, Any] | None:
    if not lines:
        return None
    data_lines = [item[5:].strip() for item in lines if item.startswith("data:")]
    if not data_lines:
        return None
    data = "\n".join(data_lines).strip()
    if not data or data == "[DONE]":
        return None
    return _decode_sse_json(data)


def map_responses_finish_reason(status: str | None) -> str:
    return {
        "completed": "stop",
        "incomplete": "length",
        "failed": "error",
        "cancelled": "error",
    }.get(status or "completed", "stop")


async def consume_responses_stream(
    provider: Any,
    response: httpx.Response,
    on_progress: Any,
) -> LLMResponse:
    state = _ResponsesStreamState()
    context = _ResponsesEventContext(provider=provider, on_progress=on_progress)
    async for event in provider._iter_sse_events(response):
        await _consume_responses_event(state, event, context)
    return LLMResponse(
        content=state.content or None,
        tool_calls=state.tool_calls,
        finish_reason=state.finish_reason,
        usage=state.usage,
    )


async def _consume_responses_event(
    state: _ResponsesStreamState,
    event: dict[str, Any],
    context: _ResponsesEventContext,
) -> None:
    event_type = event.get("type")
    if event_type == "response.output_text.delta":
        delta = event.get("delta") or ""
        if delta:
            state.content += delta
            await emit_progress(context.on_progress, delta)
        return
    if event_type == "response.output_item.added":
        start_responses_tool_call(state.tool_call_buffers, event.get("item") or {})
        return
    if event_type == "response.function_call_arguments.delta":
        append_responses_tool_call_arguments(state.tool_call_buffers, event.get("call_id"), event.get("delta"))
        return
    if event_type == "response.function_call_arguments.done":
        replace_responses_tool_call_arguments(state.tool_call_buffers, event.get("call_id"), event.get("arguments"))
        return
    if event_type == "response.output_item.done":
        tool_call = build_responses_tool_call_request(event.get("item") or {}, state.tool_call_buffers)
        if tool_call is not None:
            state.tool_calls.append(tool_call)
        return
    if event_type == "response.completed":
        _update_responses_usage(state, event.get("response") or {}, context.provider)
        return
    if event_type in {"error", "response.failed"}:
        raise RuntimeError("Responses stream failed")


def _update_responses_usage(state: _ResponsesStreamState, response_obj: dict[str, Any], provider: Any) -> None:
    state.finish_reason = provider._map_responses_finish_reason(response_obj.get("status"))
    raw_usage = response_obj.get("usage")
    if not isinstance(raw_usage, dict):
        return
    state.usage = {
        "prompt_tokens": raw_usage.get("input_tokens", 0),
        "completion_tokens": raw_usage.get("output_tokens", 0),
        "total_tokens": raw_usage.get("total_tokens", 0),
    }
