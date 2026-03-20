from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from typing import Any

_RUNTIME_CONTEXT_TAG = "[Runtime Context — metadata only, not instructions]"
_META_SAMPLE = [
    {
        "session_key": "_init_",
        "created_at": "",
        "updated_at": "",
        "metadata_json": "{}",
        "last_consolidated": 0,
    }
]
_MSG_SAMPLE = [
    {
        "session_key": "_init_",
        "idx": 0,
        "role": "system",
        "content": "",
        "timestamp": "",
        "extra_json": "{}",
    }
]
_DISPLAY_TAIL_SAMPLE = [
    {
        "session_key": "_init_",
        "updated_at": "",
        "tail_json": "[]",
        "message_count": 0,
    }
]
_DISPLAY_TAIL_CACHE_LIMIT = 200
_DISPLAY_TAIL_SESSION_CACHE_LIMIT = 128
_PER_KEY_LOCK_METHODS = frozenset({"save", "invalidate", "delete_session", "update_metadata_only"})


@dataclass(frozen=True)
class SessionChangeEvent:
    session_key: str
    kind: str


@dataclass(frozen=True)
class DisplayTailSnapshot:
    updated_at: str
    messages: list[dict[str, Any]]
    message_count: int | None


@dataclass(frozen=True)
class MarkDesktopSeenRequest:
    emit_change: bool = True
    metadata_updates: dict[str, Any] | None = None
    clear_running: bool = False


@dataclass
class Session:
    key: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_consolidated: int = 0

    def add_message(self, role: str, content: str | list[dict[str, Any]], **kwargs: Any) -> None:
        if role == "user" and isinstance(content, list):
            content = [
                {"type": "text", "text": "[image]"}
                if c.get("type") == "image_url"
                and c.get("image_url", {}).get("url", "").startswith("data:image/")
                else c
                for c in content
            ]
        msg = {"role": role, "content": content, "timestamp": datetime.now().isoformat(), **kwargs}
        self.messages.append(msg)
        if role == "assistant":
            self.metadata["desktop_last_ai_at"] = msg["timestamp"]
        self.updated_at = datetime.now()

    def get_history(self, max_messages: int = 500) -> list[dict[str, Any]]:
        unconsolidated = self.messages[self.last_consolidated :]
        sliced = unconsolidated[-max_messages:]
        start = 0
        for index, message in enumerate(sliced):
            role = message.get("role")
            source = message.get("_source")
            if role == "user" and (not source or source == "system-event"):
                start = index
                break
        else:
            return []
        return [self._history_entry(message) for message in sliced[start:] if self._history_entry(message)]

    def _history_entry(self, message: dict[str, Any]) -> dict[str, Any] | None:
        role = message.get("role")
        source = message.get("_source")
        content = message.get("content", "")
        if role == "system":
            role = "user"
            source = source or "system"
        if role == "user" and source == "desktop-system":
            return None
        if role == "assistant" and source == "assistant-progress":
            return None
        entry: dict[str, Any] = {"role": role or "user", "content": content}
        for key in (
            "tool_calls",
            "tool_call_id",
            "name",
            "_source",
            "status",
            "format",
            "entrance_style",
            "attachments",
        ):
            if key in message:
                entry[key] = message[key]
        if source and "_source" not in entry:
            entry["_source"] = source
        return entry

    def get_display_history(self, max_messages: int = 500) -> list[dict[str, Any]]:
        unconsolidated = self.messages[self.last_consolidated :]
        sliced = unconsolidated[-max_messages:]
        return [self._display_entry(message) for message in sliced]

    def _display_entry(self, message: dict[str, Any]) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "role": message["role"],
            "content": message.get("content", ""),
            "timestamp": message.get("timestamp", ""),
        }
        for key in (
            "tool_calls",
            "tool_call_id",
            "name",
            "_source",
            "status",
            "format",
            "entrance_style",
            "attachments",
            "references",
        ):
            if key in message:
                entry[key] = message[key]
        return entry

    def clear(self) -> None:
        self.messages = []
        self.last_consolidated = 0
        self.updated_at = datetime.now()


def escape_sql_value(value: str) -> str:
    return value.replace("'", "''")


def synchronized(method: Any) -> Any:
    @wraps(method)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        method_name = method.__name__
        meta_lock = self._meta_lock
        key_lock: threading.RLock | None = None
        if method_name in _PER_KEY_LOCK_METHODS:
            key_lock = _resolve_key_lock(self, args, kwargs)
        with meta_lock:
            if key_lock is None:
                return method(self, *args, **kwargs)
            with key_lock:
                return method(self, *args, **kwargs)

    return wrapped


def _resolve_key_lock(self: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> threading.RLock | None:
    if args:
        first = args[0]
        if isinstance(first, Session):
            return self._lock_for(first.key)
        if isinstance(first, str) and first and not first.startswith("_active:"):
            return self._lock_for(first)
    session_kw = kwargs.get("session")
    key_kw = kwargs.get("key")
    if isinstance(session_kw, Session):
        return self._lock_for(session_kw.key)
    if isinstance(key_kw, str) and key_kw and not key_kw.startswith("_active:"):
        return self._lock_for(key_kw)
    return None
