from __future__ import annotations

import base64
import json
from typing import Any, cast

from google.genai import types

from bao.providers.base import LLMResponse, ToolCallRequest, build_tool_call_request


def thinking_budget_from_effort(reasoning_effort: str | None) -> int | None:
    if not reasoning_effort:
        return None
    return {"low": 1024, "medium": 2048, "high": 4096}.get(reasoning_effort.strip().lower())


def split_system_instruction(messages: list[dict[str, Any]]) -> tuple[Any, list[dict[str, Any]]]:
    system_prompt = None
    filtered_messages = []
    for message in messages:
        if message.get("role") == "system":
            system_prompt = message.get("content")
        else:
            filtered_messages.append(message)
    return system_prompt, filtered_messages


def convert_messages(messages: list[dict[str, Any]]) -> list[types.Content]:
    contents: list[types.Content] = []
    pending_images: list[str] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        if role != "tool" and pending_images:
            contents.append(_pending_image_content(pending_images))
            pending_images = []
        content = _convert_message_content(message)
        if content is not None:
            contents.append(content)
        if role == "tool" and message.get("_image"):
            pending_images.append(message["_image"])
    if pending_images:
        contents.append(_pending_image_content(pending_images))
    return contents


def _convert_message_content(message: dict[str, Any]) -> types.Content | None:
    role = message.get("role")
    if role == "tool":
        return types.Content(role="user", parts=[_tool_response_part(message)])
    parts = _convert_parts(message)
    if not parts:
        return None
    return types.Content(role="model" if role == "assistant" else "user", parts=parts)


def _tool_response_part(message: dict[str, Any]) -> types.Part:
    content = message.get("content")
    tool_name = str(message.get("name") or "tool")
    result = content if isinstance(content, str) else str(content) if content else ""
    response: dict[str, Any] = {"name": tool_name, "response": {"result": result}}
    tool_call_id = message.get("tool_call_id")
    if isinstance(tool_call_id, str) and tool_call_id:
        response["id"] = tool_call_id
    return types.Part(function_response=types.FunctionResponse(**response))


def _convert_parts(message: dict[str, Any]) -> list[types.Part]:
    content = message.get("content")
    if isinstance(content, str):
        parts = [types.Part(text=content)]
    elif isinstance(content, list):
        parts = [part for item in content if (part := _convert_content_item(item)) is not None]
    else:
        parts = [types.Part(text=str(content) if content else "")]
    parts.extend(_function_call_parts(message.get("tool_calls", [])))
    return parts


def _convert_content_item(item: Any) -> types.Part | None:
    if not isinstance(item, dict):
        return None
    if item.get("type") == "text":
        return types.Part(text=item.get("text", ""))
    if item.get("type") != "image_url":
        return None
    url = (item.get("image_url") or {}).get("url", "")
    if not url.startswith("data:") or ";base64," not in url:
        return None
    header, _, b64_data = url.partition(",")
    if not b64_data:
        return None
    media_type = "image/jpeg"
    if header.startswith("data:") and ";" in header:
        media_type = header[len("data:") : header.index(";")]
    try:
        return types.Part(inline_data=types.Blob(mime_type=media_type, data=base64.b64decode(b64_data)))
    except Exception:
        return None


def _function_call_parts(tool_calls: list[dict[str, Any]]) -> list[types.Part]:
    parts = []
    for tool_call in tool_calls or []:
        function = tool_call.get("function") or {}
        parts.append(
            types.Part(
                function_call=types.FunctionCall(
                    name=function.get("name", ""),
                    args=_normalize_function_args(function.get("arguments")),
                )
            )
        )
    return parts


def _normalize_function_args(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return arguments if isinstance(arguments, dict) else {}


def _pending_image_content(images: list[str]) -> types.Content:
    parts = [types.Part(text="[screenshot from tool above]")]
    for image in images:
        parts.append(types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=base64.b64decode(image))))
    return types.Content(role="user", parts=parts)


def convert_tools(tools: list[dict[str, Any]]) -> list[types.Tool]:
    converted = []
    for tool in tools:
        function = (tool.get("function") or {}) if tool.get("type") == "function" else tool
        name = function.get("name")
        if not name:
            continue
        converted.append(
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=name,
                        description=function.get("description", ""),
                        parameters=cast(Any, function.get("parameters") if isinstance(function.get("parameters"), dict) else {}),
                    )
                ]
            )
        )
    return converted


def parse_response(response: Any) -> LLMResponse:
    candidates = getattr(response, "candidates", [])
    if not candidates:
        return LLMResponse(content="No response from Gemini", finish_reason="error")
    candidate = candidates[0]
    content = ""
    tool_calls: list[ToolCallRequest] = []
    reasoning_content: str | None = None
    for part in candidate.content.parts if candidate.content and candidate.content.parts else []:
        if part.text:
            content += part.text
        if part.thought:
            reasoning_content = (reasoning_content or "") + part.thought
        if part.function_call:
            tool_calls.append(_tool_call_from_part(part.function_call))
    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason=_finish_reason(str(candidate.finish_reason)),
        usage=_usage_from_response(response),
        reasoning_content=reasoning_content,
    )


def _tool_call_from_part(function_call: Any) -> ToolCallRequest:
    arguments_value = (
        function_call.args if isinstance(function_call.args, dict) else function_call.args
    )
    return build_tool_call_request(
        id_=getattr(function_call, "id", None) or f"call_{function_call.name}",
        name=function_call.name,
        arguments_value=arguments_value,
    )
def _finish_reason(value: str) -> str:
    return {
        "STOP": "stop",
        "MAX_TOKENS": "length",
        "SAFETY": "content_filter",
        "RECITATION": "content_filter",
        "OTHER": "error",
    }.get(value, "stop")


def _usage_from_response(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return {}
    return {
        "prompt_tokens": getattr(usage, "prompt_token_count", 0),
        "completion_tokens": getattr(usage, "candidates_token_count", 0),
        "total_tokens": getattr(usage, "total_token_count", 0),
    }
