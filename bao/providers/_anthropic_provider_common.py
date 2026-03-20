from __future__ import annotations

import json
from typing import Any

from bao.providers.base import ToolCallRequest, build_tool_call_request

_PROXY_SAFE_DEFAULT_HEADERS = {
    "User-Agent": "curl/8.7.1",
    "X-Stainless-Lang": "",
    "X-Stainless-Package-Version": "",
    "X-Stainless-OS": "",
    "X-Stainless-Arch": "",
    "X-Stainless-Runtime": "",
    "X-Stainless-Runtime-Version": "",
    "X-Stainless-Async": "",
}

_EXTENDED_THINKING_MODELS = frozenset({"claude-3-7-sonnet-20250514", "claude-sonnet-4-20250514"})


def supports_extended_thinking(model: str) -> bool:
    model_lower = model.lower()
    return any(name in model_lower for name in _EXTENDED_THINKING_MODELS)


def budget_from_reasoning_effort(reasoning_effort: str | None) -> int | None:
    if not reasoning_effort:
        return None
    return {"low": 2048, "medium": 4096, "high": 8192}.get(reasoning_effort.strip().lower())


def convert_messages(messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
    system_prompt: str | None = None
    anthropic_messages: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            system_prompt = convert_content_blocks(message.get("content"))
            continue
        converted = _convert_chat_message(message)
        if converted is not None:
            anthropic_messages.append(converted)
    return system_prompt, anthropic_messages


def _convert_chat_message(message: dict[str, Any]) -> dict[str, Any] | None:
    role = message.get("role")
    if role == "user":
        return {"role": "user", "content": convert_user_content(message.get("content"))}
    if role == "assistant":
        parts = _assistant_parts(message)
        return {"role": "assistant", "content": parts} if parts else None
    if role == "tool":
        return _tool_result_message(message)
    return None


def _assistant_parts(message: dict[str, Any]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    content = message.get("content")
    if content:
        parts.append({"type": "text", "text": str(content)})
    for tool_call in message.get("tool_calls", []) or []:
        parts.append(_tool_use_part(tool_call))
    return parts


def _tool_use_part(tool_call: dict[str, Any]) -> dict[str, Any]:
    function = tool_call.get("function") or {}
    return {
        "type": "tool_use",
        "id": tool_call.get("id", f"tool_{tool_call.get('name', 'unknown')}"),
        "name": function.get("name", ""),
        "input": _normalize_function_arguments(function.get("arguments")),
    }


def _normalize_function_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return arguments if isinstance(arguments, dict) else {}


def _tool_result_message(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    tool_content = content if isinstance(content, str) else str(content)
    tool_result_content: Any = tool_content
    image = message.get("_image")
    if image:
        tool_result_content = [
            {"type": "text", "text": tool_content},
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": image},
            },
        ]
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": message.get("tool_call_id", "unknown"),
                "content": tool_result_content,
            }
        ],
    }


def convert_user_content(content: Any) -> str | list[dict[str, Any]]:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [_convert_user_item(item) for item in content]
        filtered = [part for part in parts if part is not None]
        return filtered if filtered else ""
    return str(content)


def _convert_user_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    item_type = item.get("type")
    if item_type == "text":
        return {"type": "text", "text": item.get("text", "")}
    if item_type != "image_url":
        return None
    url = (item.get("image_url") or {}).get("url", "")
    if not url.startswith("data:"):
        return None
    header, _, data = url.partition(",")
    if not data:
        return None
    media_type = "image/jpeg"
    if header.startswith("data:") and ";" in header:
        media_type = header[len("data:") : header.index(";")]
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}


def convert_content_blocks(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    texts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            texts.append(block.get("text", ""))
    return "\n".join(texts)


def convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted = []
    for tool in tools:
        function = (tool.get("function") or {}) if tool.get("type") == "function" else tool
        name = function.get("name")
        if not name:
            continue
        converted.append(
            {
                "name": name,
                "description": function.get("description", ""),
                "input_schema": function.get("parameters") if isinstance(function.get("parameters"), dict) else {},
            }
        )
    return converted


def apply_cache_control(
    system_prompt: str | None,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> tuple[str | list[dict[str, Any]] | None, list[dict[str, Any]], list[dict[str, Any]] | None]:
    new_system = None
    if system_prompt:
        new_system = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
    new_messages = [_cacheable_message(message) for message in messages]
    new_tools = list(tools) if tools else None
    if new_tools:
        new_tools[-1] = {**new_tools[-1], "cache_control": {"type": "ephemeral"}}
    return new_system, new_messages, new_tools


def _cacheable_message(message: dict[str, Any]) -> dict[str, Any]:
    if message.get("role") != "user":
        return message
    content = message.get("content")
    if isinstance(content, str):
        content = [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]
    elif isinstance(content, list) and content:
        content = [*content[:-1], {**content[-1], "cache_control": {"type": "ephemeral"}}]
    return {**message, "content": content}


def parse_response(response: Any) -> tuple[str, list[ToolCallRequest], str | None, list[dict[str, Any]], str, dict[str, int]]:
    content = ""
    tool_calls: list[ToolCallRequest] = []
    reasoning_content: str | None = None
    thinking_blocks: list[dict[str, Any]] = []
    for block in response.content:
        if block.type == "text":
            content += block.text
        elif block.type == "tool_use":
            tool_calls.append(build_tool_call_request(block.id, block.name, block.input))
        elif block.type == "thinking":
            reasoning_content = block.thinking
            thinking_blocks.append({"type": "thinking", "thinking": block.thinking})
    finish_reason = _finish_reason(response.stop_reason)
    usage = {
        "prompt_tokens": response.usage.input_tokens,
        "completion_tokens": response.usage.output_tokens,
        "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
    }
    return content, tool_calls, reasoning_content, thinking_blocks, finish_reason, usage


def _finish_reason(stop_reason: str | None) -> str:
    if stop_reason == "end_turn":
        return "stop"
    if stop_reason == "max_tokens":
        return "length"
    if stop_reason == "tool_use":
        return "tool_calls"
    return stop_reason or "stop"
