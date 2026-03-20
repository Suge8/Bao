from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from bao.agent.reply_route import TurnContextStore
from bao.agent.reply_route_models import ReplyRouteInput
from bao.agent.tools.base import Tool
from bao.hub import TranscriptPage

_COMPACT_MESSAGE_KEYS = (
    "role",
    "content",
    "name",
    "tool_call_id",
    "status",
    "format",
    "references",
)


@dataclass(frozen=True, slots=True)
class SessionDirectoryToolContext:
    channel: str
    chat_id: str
    session_key: str | None = None
    lang: str = "en"
    message_id: str | int | None = None
    reply_metadata: dict[str, Any] | None = None


class SessionDirectoryToolBase(Tool):
    def __init__(self, directory: Any) -> None:
        self._directory = directory
        self._route = TurnContextStore("session_directory_route", ReplyRouteInput())

    def set_context(self, request: SessionDirectoryToolContext) -> None:
        self._route.set(
            ReplyRouteInput(
                channel=_normalize_channel(request.channel),
                chat_id=_normalize_text(request.chat_id),
                session_key=_normalize_text(request.session_key),
                lang=_normalize_text(request.lang) or "en",
                message_id=request.message_id,
                reply_metadata=dict(request.reply_metadata or {}),
            )
        )

    def _call_directory(self, method_name: str, **kwargs: Any) -> Any:
        method = getattr(self._directory, method_name, None)
        if not callable(method):
            return _read_plane_unavailable()
        return method(**kwargs)

    @staticmethod
    def _json(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _resolve_target(self, *, session_key: object, session_ref: object) -> tuple[str, dict[str, Any]]:
        normalized_key = _normalize_text(session_key)
        if normalized_key:
            return normalized_key, {}
        normalized_ref = _normalize_text(session_ref)
        if not normalized_ref:
            return "", {}
        result = self._call_directory("resolve_session_ref", session_ref=normalized_ref)
        if isinstance(result, str):
            return "", {}
        return _extract_session_key(result), result if isinstance(result, dict) else {}


def build_status_payload(
    *,
    session_key: str,
    entry: dict[str, Any],
    resolved: dict[str, Any],
) -> dict[str, Any]:
    source = resolved or entry
    return {
        "key": session_key,
        "ref": _normalize_text(resolved.get("session_ref")) or _normalize_text(entry.get("session_ref")),
        "title": _normalize_text((entry.get("view") or {}).get("title")) or _normalize_text(entry.get("title")),
        "channel": _normalize_text(source.get("channel")),
        "state": _normalize_text(source.get("availability")),
        "updated_at": _normalize_text(entry.get("updated_at")),
        "msgs": entry.get("message_count"),
        "has_msgs": bool(entry.get("has_messages")),
        "identity": _normalize_text(resolved.get("identity_ref")),
        "binding": _normalize_text(resolved.get("binding_key")),
    }


def build_transcript_payload(
    *,
    page: TranscriptPage,
    session_ref: str,
    raw: bool,
) -> dict[str, Any]:
    return {
        "key": page.session_key,
        "ref": _normalize_text(session_ref),
        "mode": page.mode,
        "tx": page.transcript_ref,
        "total": page.total_messages,
        "start": page.start_offset,
        "end": page.end_offset,
        "items": _project_messages(page.messages, raw=raw),
        "prev": page.previous_cursor,
        "next": page.next_cursor,
        "more_before": page.has_more_before,
        "more_after": page.has_more_after,
    }


def _project_messages(messages: list[dict[str, Any]], *, raw: bool) -> list[dict[str, Any]]:
    if raw:
        return [dict(message) for message in messages if isinstance(message, dict)]
    return [_compact_message(message) for message in messages if isinstance(message, dict)]


def _compact_message(message: dict[str, Any]) -> dict[str, Any]:
    compact = {key: message[key] for key in _COMPACT_MESSAGE_KEYS if key in message}
    if compact:
        return compact
    return dict(message)


def _extract_session_key(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("session_key", "key"):
            value = _normalize_text(payload.get(key))
            if value:
                return value
        route = payload.get("route")
        if isinstance(route, dict):
            return _normalize_text(route.get("session_key"))
        return ""
    session_key = _normalize_text(getattr(payload, "session_key", ""))
    if session_key:
        return session_key
    route = getattr(payload, "route", None)
    return _normalize_text(getattr(route, "session_key", ""))


def _read_plane_unavailable() -> str:
    return "Error: session discovery read-plane not available yet."


def _normalize_channel(value: object) -> str:
    return _normalize_text(value).lower()


def _normalize_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()
