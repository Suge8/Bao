"""Shared Mochat data structures and pure helpers."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

_socketio_available = False
try:
    import socketio

    _socketio_available = True
except ImportError:
    socketio = None
SOCKETIO_AVAILABLE = _socketio_available

_msgpack_available = False
try:
    import msgpack  # noqa: F401

    _msgpack_available = True
except ImportError:
    pass
MSGPACK_AVAILABLE = _msgpack_available

MAX_SEEN_MESSAGE_IDS = 2000
CURSOR_SAVE_DEBOUNCE_S = 0.5


@dataclass
class MochatBufferedEntry:
    raw_body: str
    author: str
    sender_name: str = ""
    sender_username: str = ""
    timestamp: int | None = None
    message_id: str = ""
    group_id: str = ""


@dataclass
class DelayState:
    entries: list[MochatBufferedEntry] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    timer: asyncio.Task[None] | None = None


@dataclass
class MochatTarget:
    id: str
    is_panel: bool


@dataclass(frozen=True)
class SyntheticEventSpec:
    message_id: str
    author: str
    content: Any
    meta: Any
    group_id: str
    converse_id: str
    timestamp: Any = None
    author_info: Any = None


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str_field(src: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = src.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _make_synthetic_event(spec: SyntheticEventSpec) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "messageId": spec.message_id,
        "author": spec.author,
        "content": spec.content,
        "meta": _safe_dict(spec.meta),
        "groupId": spec.group_id,
        "converseId": spec.converse_id,
    }
    if spec.author_info is not None:
        payload["authorInfo"] = _safe_dict(spec.author_info)
    return {
        "type": "message.add",
        "timestamp": spec.timestamp or datetime.utcnow().isoformat(),
        "payload": payload,
    }


def normalize_mochat_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if content is None:
        return ""
    try:
        return json.dumps(content, ensure_ascii=False)
    except TypeError:
        return str(content)


def resolve_mochat_target(raw: str) -> MochatTarget:
    trimmed = (raw or "").strip()
    if not trimmed:
        return MochatTarget(id="", is_panel=False)

    lowered = trimmed.lower()
    cleaned = trimmed
    forced_panel = False
    for prefix in ("mochat:", "group:", "channel:", "panel:"):
        if not lowered.startswith(prefix):
            continue
        cleaned = trimmed[len(prefix) :].strip()
        forced_panel = prefix in {"group:", "channel:", "panel:"}
        break

    if not cleaned:
        return MochatTarget(id="", is_panel=False)
    return MochatTarget(id=cleaned, is_panel=forced_panel or not cleaned.startswith("session_"))


def extract_mention_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        if isinstance(item, str):
            if item.strip():
                ids.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        for key in ("id", "userId", "_id"):
            candidate = item.get(key)
            if isinstance(candidate, str) and candidate.strip():
                ids.append(candidate.strip())
                break
    return ids


def resolve_was_mentioned(payload: dict[str, Any], agent_user_id: str) -> bool:
    meta = payload.get("meta")
    if isinstance(meta, dict):
        if meta.get("mentioned") is True or meta.get("wasMentioned") is True:
            return True
        for field_name in ("mentions", "mentionIds", "mentionedUserIds", "mentionedUsers"):
            if agent_user_id and agent_user_id in extract_mention_ids(meta.get(field_name)):
                return True
    if not agent_user_id:
        return False
    content = payload.get("content")
    if not isinstance(content, str) or not content:
        return False
    return f"<@{agent_user_id}>" in content or f"@{agent_user_id}" in content


def resolve_require_mention(config: Any, session_id: str, group_id: str) -> bool:
    groups = config.groups or {}
    for key in (group_id, session_id, "*"):
        if key and key in groups:
            return bool(groups[key].require_mention)
    return bool(config.mention.require_in_groups)


def build_buffered_body(entries: list[MochatBufferedEntry], is_group: bool) -> str:
    if not entries:
        return ""
    if len(entries) == 1:
        return entries[0].raw_body
    lines: list[str] = []
    for entry in entries:
        if not entry.raw_body:
            continue
        if is_group:
            label = entry.sender_name.strip() or entry.sender_username.strip() or entry.author
            if label:
                lines.append(f"{label}: {entry.raw_body}")
                continue
        lines.append(entry.raw_body)
    return "\n".join(lines).strip()


def parse_timestamp(value: Any) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None
