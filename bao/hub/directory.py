from __future__ import annotations

from pathlib import Path
from typing import Any

from bao.session.state import session_routing_metadata

from ._directory_models import (
    TranscriptPage,
    TranscriptReadRequest,
    build_transcript_ref,
    decode_transcript_cursor,
    encode_transcript_cursor,
)
from ._session_directory_read_plane import SessionDirectoryReadPlane
from ._session_directory_updater import get_session_directory_runtime

_DISPLAY_MESSAGE_KEYS = (
    "tool_calls",
    "tool_call_id",
    "name",
    "_source",
    "status",
    "format",
    "entrance_style",
    "attachments",
    "references",
)
_RUNTIME_CONTEXT_TAG = "[Runtime Context"


class HubDirectory:
    """Hub 只读目录：session 目录与历史查询的统一入口

    提供 list/get/status/read 等只读操作，默认不唤醒 runtime。
    是所有 session 状态查询的统一 facade。
    """

    def __init__(self, session_manager: Any) -> None:
        self._session_manager = session_manager
        self._session_directory_runtime = get_session_directory_runtime(session_manager)
        self._read_plane = SessionDirectoryReadPlane(
            session_manager=session_manager,
            runtime=self._session_directory_runtime,
        )

    @property
    def workspace(self) -> Path | None:
        workspace = getattr(self._session_manager, "workspace", None)
        if not isinstance(workspace, (str, Path)):
            return None
        return Path(str(workspace)).expanduser()

    def add_change_listener(self, listener: Any) -> None:
        add_listener = getattr(self._session_manager, "add_change_listener", None)
        if callable(add_listener):
            add_listener(listener)

    def remove_change_listener(self, listener: Any) -> None:
        remove_listener = getattr(self._session_manager, "remove_change_listener", None)
        if callable(remove_listener):
            remove_listener(listener)

    def backfill_display_tail_rows(self, keys: list[str], limit: int) -> None:
        backfill = getattr(self._session_manager, "backfill_display_tail_rows", None)
        if callable(backfill):
            backfill(keys, limit)

    def observe_origin(self, key: str, origin: Any) -> None:
        self._session_directory_runtime.updater.observe_origin(key, origin)

    def get_session_directory_record(self, key: str) -> dict[str, Any] | None:
        record = self._session_directory_runtime.store.get_record(key)
        return None if record is None else record.as_snapshot()

    def list_recent_sessions(
        self,
        *,
        limit: int | None = None,
        channel: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._read_plane.list_recent_sessions(limit=limit, channel=channel)

    def lookup_sessions(
        self,
        *,
        query: str,
        limit: int | None = None,
        channel: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._read_plane.lookup_sessions(query=query, limit=limit, channel=channel)

    def get_default_session(
        self,
        *,
        channel: str | None = None,
        scope: str | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        return self._read_plane.get_default_session(
            channel=channel,
            scope=scope,
            session_key=session_key,
        )

    def resolve_session_ref(self, *, session_ref: str) -> dict[str, Any]:
        return self._read_plane.resolve_session_ref(session_ref=session_ref)

    def resolve_delivery_target(self, *, session_ref: str) -> dict[str, Any]:
        return self._read_plane.resolve_delivery_target(session_ref=session_ref)

    @staticmethod
    def _copy_rows(raw: object) -> list[dict[str, Any]]:
        return [dict(item) for item in raw] if isinstance(raw, list) else []

    def list_sessions(self) -> list[dict[str, Any]]:
        list_sessions = getattr(self._session_manager, "list_sessions", None)
        if not callable(list_sessions):
            return []
        return self._copy_rows(list_sessions())

    def list_sessions_with_active_key(self, natural_key: str) -> tuple[list[dict[str, Any]], str]:
        list_snapshot = getattr(self._session_manager, "list_sessions_with_active_key", None)
        if not callable(list_snapshot):
            return [], ""
        snapshot = list_snapshot(str(natural_key or ""))
        if (
            not isinstance(snapshot, tuple)
            or len(snapshot) != 2
            or not isinstance(snapshot[0], list)
            or not isinstance(snapshot[1], str)
        ):
            return [], ""
        return self._copy_rows(snapshot[0]), snapshot[1]

    def get_session(self, key: str) -> dict[str, Any] | None:
        get_entry = getattr(self._session_manager, "get_session_list_entry", None)
        if callable(get_entry):
            entry = get_entry(str(key or ""))
            return dict(entry) if isinstance(entry, dict) else None
        return next((item for item in self.list_sessions() if str(item.get("key", "")) == str(key or "")), None)

    def get_status(self, key: str) -> dict[str, Any] | None:
        return self.get_session(key)

    def list_children(self, parent_session_key: str) -> list[dict[str, Any]]:
        list_children = getattr(self._session_manager, "list_child_sessions", None)
        if callable(list_children):
            raw = list_children(str(parent_session_key or ""))
            return self._copy_rows(raw)
        parent_key = str(parent_session_key or "")
        if not parent_key:
            return []
        children: list[dict[str, Any]] = []
        for item in self.list_sessions():
            metadata = item.get("metadata")
            if isinstance(metadata, dict) and session_routing_metadata(metadata).parent_session_key == parent_key:
                children.append(item)
        return children

    def peek_transcript_tail(self, key: str, limit: int) -> list[dict[str, Any]] | None:
        peek_tail = getattr(self._session_manager, "peek_tail_messages", None)
        if not callable(peek_tail):
            return None
        snapshot = peek_tail(str(key or ""), int(limit or 0))
        if not isinstance(snapshot, list):
            return None
        return [dict(message) for message in snapshot if isinstance(message, dict)]

    def read_transcript(self, key: str, request: TranscriptReadRequest | None = None) -> TranscriptPage:
        normalized_key = str(key or "")
        read_request = request or TranscriptReadRequest()
        if read_request.mode == "tail" and not read_request.cursor:
            return self._read_tail_page(normalized_key, read_request)
        transcript = self._read_full_transcript(normalized_key)
        total_messages = len(transcript)
        updated_at = self._session_updated_at(normalized_key)
        transcript_ref = build_transcript_ref(normalized_key, updated_at, total_messages)
        self._assert_transcript_ref(read_request.transcript_ref, transcript_ref)
        start_offset, end_offset = self._resolve_window(read_request, total_messages)
        messages = [dict(message) for message in transcript[start_offset:end_offset]]
        limit = read_request.normalized_limit()
        return TranscriptPage(
            session_key=normalized_key,
            mode=read_request.mode,
            transcript_ref=transcript_ref,
            total_messages=total_messages,
            start_offset=start_offset,
            end_offset=end_offset,
            messages=messages,
            previous_cursor=self._previous_cursor(start_offset, limit),
            next_cursor=encode_transcript_cursor(end_offset) if end_offset < total_messages else "",
            has_more_before=start_offset > 0,
            has_more_after=end_offset < total_messages,
        )

    def _read_tail_page(self, key: str, request: TranscriptReadRequest) -> TranscriptPage:
        get_tail = getattr(self._session_manager, "get_tail_messages", None)
        messages: list[dict[str, Any]] | None = None
        if callable(get_tail):
            raw = get_tail(key, request.normalized_limit())
            if isinstance(raw, list):
                messages = [dict(message) for message in raw]
        if messages is None:
            full_transcript = self._read_full_transcript(key)
            limit = request.normalized_limit()
            messages = full_transcript[-limit:] if limit > 0 else full_transcript
        entry = self.get_session(key) or {}
        total_messages = self._coerce_count(entry.get("message_count"))
        if total_messages is None:
            total_messages = len(messages)
        total_messages = max(total_messages, len(messages))
        updated_at = str(entry.get("updated_at") or "")
        start_offset = max(total_messages - len(messages), 0)
        transcript_ref = build_transcript_ref(key, updated_at, total_messages)
        self._assert_transcript_ref(request.transcript_ref, transcript_ref)
        limit = request.normalized_limit()
        return TranscriptPage(
            session_key=key,
            mode=request.mode,
            transcript_ref=transcript_ref,
            total_messages=total_messages,
            start_offset=start_offset,
            end_offset=start_offset + len(messages),
            messages=messages,
            previous_cursor=self._previous_cursor(start_offset, limit),
            next_cursor="",
            has_more_before=start_offset > 0,
            has_more_after=False,
        )

    def _read_full_transcript(self, key: str) -> list[dict[str, Any]]:
        get_display_messages = getattr(self._session_manager, "get_display_messages", None)
        if callable(get_display_messages):
            raw = get_display_messages(key)
            if isinstance(raw, list):
                return self._copy_rows(raw)
        load_session = getattr(self._session_manager, "get_or_create", None)
        if not callable(load_session):
            return []
        session = load_session(key)
        messages = getattr(session, "messages", None)
        last_consolidated = int(getattr(session, "last_consolidated", 0) or 0)
        if not isinstance(messages, list):
            get_display_history = getattr(session, "get_display_history", None)
            if callable(get_display_history):
                raw = get_display_history()
                return self._copy_rows(raw)
            return []
        return [
            self._display_message(message)
            for message in messages[last_consolidated:]
            if self._include_message(message)
        ]

    @staticmethod
    def _include_message(message: object) -> bool:
        if not isinstance(message, dict):
            return False
        if message.get("role") != "user":
            return True
        content = message.get("content")
        return not (isinstance(content, str) and content.startswith(_RUNTIME_CONTEXT_TAG))

    @staticmethod
    def _display_message(message: dict[str, Any]) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "role": message.get("role", "user"),
            "content": message.get("content", ""),
            "timestamp": message.get("timestamp", ""),
        }
        for key in _DISPLAY_MESSAGE_KEYS:
            if key in message:
                entry[key] = message[key]
        return entry

    @staticmethod
    def _coerce_count(value: object) -> int | None:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, float):
            return max(0, int(value))
        if isinstance(value, str) and value.strip().isdigit():
            return max(0, int(value.strip()))
        return None

    def _session_updated_at(self, key: str) -> str:
        entry = self.get_session(key) or {}
        return str(entry.get("updated_at") or "")

    @staticmethod
    def _assert_transcript_ref(request_ref: str, current_ref: str) -> None:
        if request_ref and request_ref != current_ref:
            raise ValueError("transcript_ref_mismatch")

    @staticmethod
    def _resolve_window(request: TranscriptReadRequest, total_messages: int) -> tuple[int, int]:
        if request.mode == "full":
            return 0, total_messages
        limit = request.normalized_limit()
        if request.mode == "tail":
            return max(total_messages - limit, 0), total_messages
        cursor_offset = decode_transcript_cursor(request.cursor) or 0
        start_offset = min(max(cursor_offset, 0), total_messages)
        return start_offset, min(start_offset + limit, total_messages)

    @staticmethod
    def _previous_cursor(start_offset: int, limit: int) -> str:
        if start_offset <= 0 or limit <= 0:
            return ""
        return encode_transcript_cursor(max(start_offset - limit, 0))
