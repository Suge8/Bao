"""Shared utilities for OpenAI Responses API compatibility.

Converts between OpenAI Chat Completions message format and Responses API
input format. Used by OpenAICompatibleProvider for auto-probe/fallback.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from bao.providers.base import ToolCallRequest


def convert_messages_to_responses(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Convert Chat Completions messages to Responses API ``input`` format.

    Returns ``(system_prompt, input_items)``.
    """
    system_prompt = ""
    input_items: list[dict[str, Any]] = []
    pending_images: list[str] = []

    for idx, msg in enumerate(messages):
        role = msg.get("role")
        content = msg.get("content")

        if role == "system":
            if isinstance(content, str):
                system_prompt = content
            elif isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                    elif isinstance(item, str):
                        parts.append(item)
                system_prompt = "".join(parts).strip()
            else:
                system_prompt = ""
            continue

        # Flush pending screenshot images before non-tool message
        if role != "tool" and pending_images:
            input_items.append(_build_pending_image_input(pending_images))
            pending_images = []

        if role == "user":
            input_items.append(_convert_user_message(content))
            continue

        if role == "assistant":
            if isinstance(content, str) and content:
                input_items.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": content}],
                        "status": "completed",
                        "id": f"msg_{idx}",
                    }
                )
            for tool_call in msg.get("tool_calls", []) or []:
                fn = tool_call.get("function") or {}
                call_id, item_id = _split_tool_call_id(tool_call.get("id"))
                call_id = _normalize_call_id(call_id or f"call_{idx}")
                item_id = item_id or f"fc_{idx}"
                input_items.append(
                    {
                        "type": "function_call",
                        "id": item_id,
                        "call_id": call_id,
                        "name": fn.get("name"),
                        "arguments": fn.get("arguments") or "{}",
                    }
                )
            continue

        if role == "tool":
            call_id, _ = _split_tool_call_id(msg.get("tool_call_id"))
            call_id = _normalize_call_id(call_id)
            output_text = (
                content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            )
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output_text,
                }
            )
            img_b64 = msg.get("_image")
            if img_b64:
                pending_images.append(img_b64)
            continue

    # Flush any remaining images at end
    if pending_images:
        input_items.append(_build_pending_image_input(pending_images))

    return system_prompt, input_items


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


def _convert_user_message(content: Any) -> dict[str, Any]:
    if isinstance(content, str):
        return {"role": "user", "content": [{"type": "input_text", "text": content}]}
    if isinstance(content, list):
        converted: list[dict[str, Any]] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                converted.append({"type": "input_text", "text": item.get("text", "")})
            elif item.get("type") == "image_url":
                url = (item.get("image_url") or {}).get("url")
                if url:
                    converted.append({"type": "input_image", "image_url": url, "detail": "auto"})
        if converted:
            return {"role": "user", "content": converted}
    return {"role": "user", "content": [{"type": "input_text", "text": ""}]}


def _build_pending_image_input(images_b64: list[str]) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {"type": "input_text", "text": "[screenshot from tool above]"},
    ]
    for image_b64 in images_b64:
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{image_b64}",
                "detail": "auto",
            }
        )
    return {"role": "user", "content": content}


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
    call_id = item.get("call_id")
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
    if not call_id:
        return
    buf = tool_call_buffers.get(str(call_id))
    if buf is None:
        return
    buf["arguments"] += str(delta or "")


def replace_responses_tool_call_arguments(
    tool_call_buffers: dict[str, dict[str, Any]], call_id: Any, arguments: Any
) -> None:
    if not call_id:
        return
    buf = tool_call_buffers.get(str(call_id))
    if buf is None:
        return
    buf["arguments"] = arguments or ""


def build_responses_tool_call_request(
    item: dict[str, Any],
    tool_call_buffers: dict[str, dict[str, Any]] | None = None,
) -> ToolCallRequest | None:
    if item.get("type") != "function_call":
        return None
    call_id = item.get("call_id")
    if not call_id:
        return None
    buf = (tool_call_buffers or {}).get(call_id) or {}
    args_raw = buf.get("arguments") or item.get("arguments") or "{}"
    return ToolCallRequest(
        id=build_internal_tool_call_id(call_id, buf.get("id") or item.get("id") or "fc_0"),
        name=str(buf.get("name") or item.get("name") or "unknown_tool"),
        arguments=_parse_tool_call_arguments(args_raw),
    )


def build_internal_tool_call_id(tool_call_id: Any, item_id: Any) -> str:
    call_id, _ = _split_tool_call_id(tool_call_id)
    normalized_call_id = _normalize_call_id(call_id)
    normalized_item_id = str(item_id or "fc_0").strip() or "fc_0"
    return f"{normalized_call_id}|{normalized_item_id}"


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
