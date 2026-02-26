"""Shared utilities for OpenAI Responses API compatibility.

Converts between OpenAI Chat Completions message format and Responses API
input format. Used by OpenAICompatibleProvider for auto-probe/fallback.
"""

from __future__ import annotations

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
            system_prompt = content if isinstance(content, str) else ""
            continue

        # Flush pending screenshot images before non-tool message
        if role != "tool" and pending_images:
            img_content: list[dict[str, Any]] = [
                {"type": "input_text", "text": "[screenshot from tool above]"},
            ]
            for ib64 in pending_images:
                img_content.append({
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{ib64}",
                    "detail": "auto",
                })
            input_items.append({"role": "user", "content": img_content})
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
                call_id = call_id or f"call_{idx}"
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
        img_content = [
            {"type": "input_text", "text": "[screenshot from tool above]"},
        ]
        for ib64 in pending_images:
            img_content.append({
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{ib64}",
                "detail": "auto",
            })
        input_items.append({"role": "user", "content": img_content})

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

        call_id = item.get("call_id") or "call_0"
        args_raw = item.get("arguments") or "{}"
        try:
            args = json.loads(args_raw)
        except Exception:
            args = {"raw": args_raw}
        tool_calls.append(
            ToolCallRequest(
                id=f"{call_id}|{item.get('id') or 'fc_0'}",
                name=item.get("name"),
                arguments=args,
            )
        )

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


def _split_tool_call_id(tool_call_id: Any) -> tuple[str, str | None]:
    if isinstance(tool_call_id, str) and tool_call_id:
        if "|" in tool_call_id:
            call_id, item_id = tool_call_id.split("|", 1)
            return call_id, item_id or None
        return tool_call_id, None
    return "call_0", None


_FINISH_REASON_MAP = {
    "completed": "stop",
    "incomplete": "length",
    "failed": "error",
    "cancelled": "error",
}


def _map_finish_reason(status: str | None) -> str:
    return _FINISH_REASON_MAP.get(status or "completed", "stop")
