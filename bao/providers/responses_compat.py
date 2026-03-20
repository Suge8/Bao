"""Shared utilities for OpenAI Responses API compatibility.

Converts between OpenAI Chat Completions message format and Responses API
input format. Used by OpenAICompatibleProvider for auto-probe/fallback.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from bao.providers._responses_compat_convert import (
    convert_messages_to_responses as _convert_messages_to_responses,
)
from bao.providers.base import ToolCallRequest


def convert_messages_to_responses(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Convert Chat Completions messages to Responses API ``input`` format."""
    system_prompt, input_items = _convert_messages_to_responses(
        messages,
        normalize_call_id=_normalize_call_id,
        split_tool_call_id=_split_tool_call_id,
    )
    return system_prompt, sanitize_responses_input_items(input_items)


def convert_tools_to_responses(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert OpenAI function-calling tool schema to Responses API flat format."""
    converted: list[dict[str, Any]] = []
    for tool in tools:
        fn = (tool.get("function") or {}) if tool.get("type") == "function" else tool
        name = fn.get("name")
        if not name:
            continue
        parameters = fn.get("parameters")
        converted.append(
            {
                "type": "function",
                "name": name,
                "description": fn.get("description") or "",
                "parameters": parameters if isinstance(parameters, dict) else {},
            }
        )
    return converted


def parse_responses_json(
    data: dict[str, Any],
) -> tuple[str, list[ToolCallRequest], str, dict[str, int]]:
    """Parse a non-streaming Responses API JSON response.

    Returns ``(content, tool_calls, finish_reason, usage)``.
    """
    content = ""
    tool_calls: list[ToolCallRequest] = []

    for item in data.get("output", []):
        item_type = item.get("type")
        if item_type == "message":
            for block in item.get("content", []):
                if block.get("type") == "output_text":
                    content += block.get("text", "")
            continue
        if item_type != "function_call":
            continue
        tool_call = build_responses_tool_call_request(item)
        if tool_call is not None:
            tool_calls.append(tool_call)

    status = data.get("status", "completed")
    finish_reason = _map_finish_reason(status)

    usage: dict[str, int] = {}
    raw_usage = data.get("usage")
    if isinstance(raw_usage, dict):
        usage = {
            "prompt_tokens": raw_usage.get("input_tokens", 0),
            "completion_tokens": raw_usage.get("output_tokens", 0),
            "total_tokens": raw_usage.get("total_tokens", 0),
        }

    return content, tool_calls, finish_reason, usage


def _split_tool_call_id(tool_call_id: Any) -> tuple[str, str | None]:
    if isinstance(tool_call_id, str) and tool_call_id:
        if "|" in tool_call_id:
            call_id, item_id = tool_call_id.split("|", 1)
            return call_id, item_id or None
        return tool_call_id, None
    return "call_0", None


def start_responses_tool_call(
    tool_call_buffers: dict[str, dict[str, Any]], item: dict[str, Any]
) -> None:
    if item.get("type") != "function_call":
        return
    call_id = _normalize_responses_call_id(item.get("call_id"))
    if not call_id:
        return
    tool_call_buffers[call_id] = {
        "id": item.get("id") or "fc_0",
        "name": item.get("name") or "unknown_tool",
        "arguments": item.get("arguments") or "",
    }


def append_responses_tool_call_arguments(
    tool_call_buffers: dict[str, dict[str, Any]], call_id: Any, delta: Any
) -> None:
    normalized_call_id = _normalize_responses_call_id(call_id)
    if not normalized_call_id:
        return
    buf = tool_call_buffers.get(normalized_call_id)
    if buf is None:
        return
    buf["arguments"] += str(delta or "")


def replace_responses_tool_call_arguments(
    tool_call_buffers: dict[str, dict[str, Any]], call_id: Any, arguments: Any
) -> None:
    normalized_call_id = _normalize_responses_call_id(call_id)
    if not normalized_call_id:
        return
    buf = tool_call_buffers.get(normalized_call_id)
    if buf is None:
        return
    buf["arguments"] = arguments or ""


def build_responses_tool_call_request(
    item: dict[str, Any],
    tool_call_buffers: dict[str, dict[str, Any]] | None = None,
) -> ToolCallRequest | None:
    if item.get("type") != "function_call":
        return None
    call_id = _normalize_responses_call_id(item.get("call_id"))
    if not call_id:
        return None
    buf = (tool_call_buffers or {}).get(call_id) or {}
    args_raw = buf.get("arguments") or item.get("arguments") or "{}"
    return ToolCallRequest(
        id=build_internal_tool_call_id(call_id, buf.get("id") or item.get("id") or "fc_0"),
        name=str(buf.get("name") or item.get("name") or "unknown_tool"),
        arguments=_parse_tool_call_arguments(args_raw),
    )


def sanitize_responses_input_items(
    input_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize outgoing Responses input items before the API boundary."""
    sanitized: list[dict[str, Any]] = []
    for item in input_items:
        if not isinstance(item, dict):
            continue
        clean = dict(item)
        item_type = clean.get("type")
        if item_type in {"function_call", "function_call_output"}:
            clean["call_id"] = _normalize_responses_call_id(clean.get("call_id"))
        sanitized.append(clean)
    return sanitized


def build_internal_tool_call_id(tool_call_id: Any, item_id: Any) -> str:
    call_id, _ = _split_tool_call_id(tool_call_id)
    normalized_call_id = _normalize_call_id(call_id)
    normalized_item_id = str(item_id or "fc_0").strip() or "fc_0"
    return f"{normalized_call_id}|{normalized_item_id}"


def _normalize_responses_call_id(value: Any) -> str:
    call_id, _ = _split_tool_call_id(value)
    return _normalize_call_id(call_id)


def _normalize_call_id(call_id: str) -> str:
    raw = str(call_id or "call_0").strip() or "call_0"
    if len(raw) <= 64:
        return raw
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    prefix = raw[:47]
    return f"{prefix}_{digest}"


def _parse_tool_call_arguments(arguments_raw: Any) -> dict[str, Any]:
    if not isinstance(arguments_raw, str):
        return arguments_raw if isinstance(arguments_raw, dict) else {}
    try:
        parsed = json.loads(arguments_raw)
    except Exception:
        return {"raw": arguments_raw}
    return parsed if isinstance(parsed, dict) else {}


_FINISH_REASON_MAP = {
    "completed": "stop",
    "incomplete": "length",
    "failed": "error",
    "cancelled": "error",
}


def _map_finish_reason(status: str | None) -> str:
    return _FINISH_REASON_MAP.get(status or "completed", "stop")
