"""Shared DingTalk helpers."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

_dingtalk_available = False
try:
    importlib.import_module("dingtalk_stream")
    importlib.import_module("dingtalk_stream.chatbot")
    _dingtalk_available = True
except ImportError:
    pass

DINGTALK_AVAILABLE = _dingtalk_available
DINGTALK_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
DINGTALK_AUDIO_EXTS = {".amr", ".mp3", ".wav", ".ogg", ".m4a", ".aac"}
DINGTALK_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def _is_http_url(value: str) -> bool:
    return urlparse(value).scheme in ("http", "https")


def _guess_upload_type(media_ref: str) -> str:
    ext = Path(urlparse(media_ref).path).suffix.lower()
    if ext in DINGTALK_IMAGE_EXTS:
        return "image"
    if ext in DINGTALK_AUDIO_EXTS:
        return "voice"
    if ext in DINGTALK_VIDEO_EXTS:
        return "video"
    return "file"


def _guess_filename(media_ref: str, upload_type: str) -> str:
    name = os.path.basename(urlparse(media_ref).path)
    return name or {
        "image": "image.jpg",
        "voice": "audio.amr",
        "video": "video.mp4",
    }.get(upload_type, "file.bin")


def _extract_message_content(chatbot_msg: Any, raw: Any) -> str:
    if getattr(chatbot_msg, "text", None):
        content = (chatbot_msg.text.content or "").strip()
        if content:
            return content
    if not isinstance(raw, dict):
        return ""

    text_content = str(raw.get("text", {}).get("content", "")).strip()
    if text_content:
        return text_content
    return str((raw.get("extensions") or {}).get("content", {}).get("recognition", "")).strip()


def _extract_conversation(raw: Any) -> tuple[str | None, str | None]:
    if not isinstance(raw, dict):
        return None, None
    conversation_type = str(raw.get("conversationType")) if raw.get("conversationType") else None
    conversation_id = str(raw.get("conversationId") or raw.get("openConversationId") or "") or None
    return conversation_type, conversation_id


def _resolve_local_media_path(media_ref: str, os_name: str | None = None) -> Path:
    if not media_ref.startswith("file://"):
        return Path(os.path.expanduser(media_ref))

    parsed = urlparse(media_ref)
    host = parsed.netloc
    path_part = unquote(parsed.path or "")
    target_os = os_name or os.name

    if target_os == "nt":
        if host and host.lower() != "localhost":
            path_text = f"//{host}{path_part}"
        else:
            path_text = path_part
        if len(path_text) >= 3 and path_text[0] == "/" and path_text[2] == ":":
            path_text = path_text[1:]
        return Path(path_text)

    if host and host.lower() != "localhost":
        return Path(f"//{host}{path_part}")
    return Path(path_part)


def _build_chat_id(
    sender_id: str,
    conversation_type: str | None,
    conversation_id: str | None,
) -> str:
    if conversation_type == "2" and conversation_id:
        return f"group:{conversation_id}"
    return sender_id


def _build_metadata(
    sender_name: str,
    conversation_type: str | None,
    conversation_id: str | None,
) -> dict[str, Any]:
    return {
        "sender_name": sender_name,
        "platform": "dingtalk",
        "conversation_type": conversation_type,
        "conversation_id": conversation_id,
    }
