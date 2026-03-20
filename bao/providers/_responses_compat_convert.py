"""Conversion helpers for OpenAI Responses API compatibility."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _ToolCallIdOps:
    normalize: Any
    split: Any


@dataclass(frozen=True)
class _AssistantItemContext:
    idx: int
    ops: _ToolCallIdOps


def convert_messages_to_responses(
    messages: list[dict[str, Any]],
    *,
    normalize_call_id,
    split_tool_call_id,
) -> tuple[str, list[dict[str, Any]]]:
    call_id_ops = _ToolCallIdOps(normalize=normalize_call_id, split=split_tool_call_id)
    system_prompt = ""
    input_items: list[dict[str, Any]] = []
    pending_images: list[str] = []

    for idx, msg in enumerate(messages):
        role = msg.get("role")
        content = msg.get("content")

        if role == "system":
            system_prompt = _extract_system_prompt(content)
            continue

        pending_images = _flush_pending_images(input_items, pending_images, role)
        if role == "user":
            input_items.append(_convert_user_message(content))
            continue
        if role == "assistant":
            _append_assistant_items(
                input_items,
                msg,
                _AssistantItemContext(idx=idx, ops=call_id_ops),
            )
            continue
        if role == "tool":
            input_items.append(_build_tool_output_item(content, msg.get("tool_call_id"), call_id_ops))
            img_b64 = msg.get("_image")
            if img_b64:
                pending_images.append(img_b64)

    if pending_images:
        input_items.append(_build_pending_image_input(pending_images))
    return system_prompt, input_items


def _extract_system_prompt(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
        elif isinstance(item, str):
            parts.append(item)
    return "".join(parts).strip()


def _flush_pending_images(
    input_items: list[dict[str, Any]],
    pending_images: list[str],
    role: Any,
) -> list[str]:
    if role == "tool" or not pending_images:
        return pending_images
    input_items.append(_build_pending_image_input(pending_images))
    return []


def _append_assistant_items(
    input_items: list[dict[str, Any]],
    assistant_message: dict[str, Any],
    ctx: _AssistantItemContext,
) -> None:
    content = assistant_message.get("content")
    tool_calls = assistant_message.get("tool_calls")
    message_item = _build_assistant_message(content, ctx.idx)
    if message_item is not None:
        input_items.append(message_item)
    for tool_call in tool_calls or []:
        item = _build_assistant_tool_call_item(tool_call, ctx)
        if item is not None:
            input_items.append(item)


def _build_assistant_message(content: Any, idx: int) -> dict[str, Any] | None:
    if not isinstance(content, str) or not content:
        return None
    return {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": content}],
        "status": "completed",
        "id": f"msg_{idx}",
    }


def _build_assistant_tool_call_item(tool_call: Any, ctx: _AssistantItemContext) -> dict[str, Any] | None:
    if not isinstance(tool_call, dict):
        return None
    fn = tool_call.get("function") or {}
    call_id, item_id = ctx.ops.split(tool_call.get("id"))
    return {
        "type": "function_call",
        "id": item_id or f"fc_{ctx.idx}",
        "call_id": ctx.ops.normalize(call_id or f"call_{ctx.idx}"),
        "name": fn.get("name"),
        "arguments": fn.get("arguments") or "{}",
    }


def _build_tool_output_item(
    content: Any,
    tool_call_id: Any,
    ops: _ToolCallIdOps,
) -> dict[str, Any]:
    call_id, _ = ops.split(tool_call_id)
    output_text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return {
        "type": "function_call_output",
        "call_id": ops.normalize(call_id),
        "output": output_text,
    }


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
    content: list[dict[str, Any]] = [{"type": "input_text", "text": "[screenshot from tool above]"}]
    for image_b64 in images_b64:
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{image_b64}",
                "detail": "auto",
            }
        )
    return {"role": "user", "content": content}
