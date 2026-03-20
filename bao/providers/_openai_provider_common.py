from __future__ import annotations

import re
from typing import Any

import httpx

_ALLOWED_MSG_KEYS = frozenset({"role", "content", "tool_calls", "tool_call_id", "name"})
_PROBE_FALLBACK_CODES = frozenset({404, 405, 501})
_CJK_CHAR_RE = re.compile(r"[\u3400-\u9FFF]")


def _normalize_openai_reasoning_effort(value: Any, *, allow_off: bool) -> str | None:
    if not isinstance(value, str):
        return None
    effort = value.strip().lower()
    if effort in {"low", "medium", "high"}:
        return effort
    if allow_off and effort == "off":
        return "none"
    return None


def _normalize_service_tier(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    service_tier = value.strip().lower()
    return service_tier or None


def _system_prompt_seems_ignored(system_prompt: str, content: str | None) -> bool:
    if not system_prompt:
        return False
    text = (content or "").strip()
    if not text:
        return False
    if "You are Bao" in system_prompt and re.search(r"\bCodex\b", text, re.I):
        return True
    if "Respond in 中文" in system_prompt and not _CJK_CHAR_RE.search(text):
        return True
    return bool(re.search(r"what do you want to work on\?", text, re.I))


class _ResponsesHTTPStatusError(RuntimeError):
    def __init__(self, response: httpx.Response):
        self.status_code = response.status_code
        self.response = response
        super().__init__(f"Responses API HTTP {response.status_code}: {response.text[:500]}")


def apply_cache_control(
    supports_prompt_caching: bool,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    if not supports_prompt_caching:
        return messages, tools
    return _cacheable_messages(messages), _cacheable_tools(tools)


def _cacheable_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    new_messages = []
    for msg in messages:
        if msg.get("role") != "system":
            new_messages.append(msg)
            continue
        new_messages.append({**msg, "content": _cacheable_content_blocks(msg.get("content"))})
    return new_messages


def _cacheable_content_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]
    if isinstance(content, list) and content:
        blocks = list(content)
        last = blocks[-1]
        if isinstance(last, dict):
            blocks[-1] = {**last, "cache_control": {"type": "ephemeral"}}
            return blocks
        blocks.append({"type": "text", "text": str(last), "cache_control": {"type": "ephemeral"}})
        return blocks
    return [{"type": "text", "text": str(content or ""), "cache_control": {"type": "ephemeral"}}]


def _cacheable_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return tools
    new_tools = list(tools)
    new_tools[-1] = {**new_tools[-1], "cache_control": {"type": "ephemeral"}}
    return new_tools


def sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    pending_images: list[str] = []
    for msg in messages:
        clean = _sanitize_single_message(msg)
        if clean.get("role") != "tool" and pending_images:
            sanitized.append(_pending_image_message(pending_images))
            pending_images = []
        sanitized.append(clean)
        image = msg.get("_image")
        if image and clean.get("role") == "tool":
            pending_images.append(image)
    if pending_images:
        sanitized.append(_pending_image_message(pending_images))
    return sanitized


def _sanitize_single_message(message: dict[str, Any]) -> dict[str, Any]:
    clean = {key: value for key, value in message.items() if key in _ALLOWED_MSG_KEYS}
    if clean.get("role") == "tool":
        clean.pop("name", None)
    if clean.get("role") == "assistant" and "content" not in clean:
        clean["content"] = None
    return clean


def _pending_image_message(images: list[str]) -> dict[str, Any]:
    parts: list[dict[str, Any]] = [{"type": "text", "text": "[screenshot from tool above]"}]
    for image in images:
        parts.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}})
    return {"role": "user", "content": parts}
