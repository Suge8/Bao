"""Feishu content extraction helpers."""

from __future__ import annotations

import json
from typing import Any

MSG_TYPE_MAP = {
    "image": "[image]",
    "audio": "[audio]",
    "file": "[file]",
    "sticker": "[sticker]",
}


def _extract_share_card_content(content_json: dict[str, Any], msg_type: str) -> str:
    parts: list[str] = []

    if msg_type == "share_chat":
        parts.append(f"[shared chat: {content_json.get('chat_id', '')}]")
    elif msg_type == "share_user":
        parts.append(f"[shared user: {content_json.get('user_id', '')}]")
    elif msg_type == "interactive":
        parts.extend(_extract_interactive_content(content_json))
    elif msg_type == "share_calendar_event":
        parts.append(f"[shared calendar event: {content_json.get('event_key', '')}]")
    elif msg_type == "system":
        parts.append("[system message]")
    elif msg_type == "merge_forward":
        parts.append("[merged forward messages]")

    return "\n".join(parts) if parts else f"[{msg_type}]"


def _extract_interactive_content(content: dict[str, Any]) -> list[str]:
    parts: list[str] = []

    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return [content] if content.strip() else []

    if not isinstance(content, dict):
        return parts

    title = content.get("title")
    if isinstance(title, dict):
        title_content = title.get("content", "") or title.get("text", "")
        if title_content:
            parts.append(f"title: {title_content}")
    elif isinstance(title, str):
        parts.append(f"title: {title}")

    elements = content.get("elements")
    if isinstance(elements, list):
        for group in elements:
            if isinstance(group, dict):
                parts.extend(_extract_element_content(group))
            elif isinstance(group, list):
                for element in group:
                    parts.extend(_extract_element_content(element))

    card = content.get("card", {})
    if card:
        parts.extend(_extract_interactive_content(card))

    header = content.get("header", {})
    if header:
        header_title = header.get("title", {})
        if isinstance(header_title, dict):
            header_text = header_title.get("content", "") or header_title.get("text", "")
            if header_text:
                parts.append(f"title: {header_text}")

    return parts


def _extract_element_content(element: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    if not isinstance(element, dict):
        return parts

    tag = element.get("tag", "")
    if tag in ("markdown", "lark_md"):
        content = element.get("content", "")
        return [content] if content else parts
    if tag == "div":
        return _extract_div_content(element)
    if tag == "a":
        return _extract_link_content(element)
    if tag == "button":
        return _extract_button_content(element)
    if tag == "img":
        alt = element.get("alt", {})
        return [alt.get("content", "[image]") if isinstance(alt, dict) else "[image]"]
    if tag == "note":
        for note_element in element.get("elements", []):
            parts.extend(_extract_element_content(note_element))
        return parts
    if tag == "column_set":
        for column in element.get("columns", []):
            for column_element in column.get("elements", []):
                parts.extend(_extract_element_content(column_element))
        return parts
    if tag == "plain_text":
        content = element.get("content", "")
        return [content] if content else parts
    for nested in element.get("elements", []):
        parts.extend(_extract_element_content(nested))
    return parts


def _extract_div_content(element: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    text = element.get("text", {})
    if isinstance(text, dict):
        text_content = text.get("content", "") or text.get("text", "")
        if text_content:
            parts.append(text_content)
    elif isinstance(text, str):
        parts.append(text)
    for field in element.get("fields", []):
        if not isinstance(field, dict):
            continue
        field_text = field.get("text", {})
        if isinstance(field_text, dict):
            content = field_text.get("content", "")
            if content:
                parts.append(content)
    return parts


def _extract_link_content(element: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    href = element.get("href", "")
    text = element.get("text", "")
    if href:
        parts.append(f"link: {href}")
    if text:
        parts.append(text)
    return parts


def _extract_button_content(element: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    text = element.get("text", {})
    if isinstance(text, dict):
        content = text.get("content", "")
        if content:
            parts.append(content)
    url = element.get("url", "") or element.get("multi_url", {}).get("url", "")
    if url:
        parts.append(f"link: {url}")
    return parts


def _extract_post_text(content_json: dict[str, Any]) -> str:
    def extract_from_lang(lang_content: Any) -> str | None:
        if not isinstance(lang_content, dict):
            return None
        title = lang_content.get("title", "")
        content_blocks = lang_content.get("content", [])
        if not isinstance(content_blocks, list):
            return None
        text_parts: list[str] = []
        if title:
            text_parts.append(title)
        for block in content_blocks:
            if not isinstance(block, list):
                continue
            for element in block:
                if not isinstance(element, dict):
                    continue
                tag = element.get("tag")
                if tag == "text":
                    text_parts.append(element.get("text", ""))
                elif tag == "a":
                    text_parts.append(element.get("text", ""))
                elif tag == "at":
                    text_parts.append(f"@{element.get('user_name', 'user')}")
        return " ".join(text_parts).strip() if text_parts else None

    post_root = content_json.get("post") if isinstance(content_json, dict) else None
    if not isinstance(post_root, dict):
        post_root = content_json if isinstance(content_json, dict) else {}

    if "content" in post_root:
        result = extract_from_lang(post_root)
        if result:
            return result

    for lang_key in ("zh_cn", "en_us", "ja_jp"):
        result = extract_from_lang(post_root.get(lang_key))
        if result:
            return result

    for value in post_root.values():
        if isinstance(value, dict):
            result = extract_from_lang(value)
            if result:
                return result

    return ""
