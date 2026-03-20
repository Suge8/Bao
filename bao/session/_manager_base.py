from __future__ import annotations

import json
import threading
from collections import OrderedDict
from collections.abc import Callable
from hashlib import blake2b
from pathlib import Path
from typing import Any

from bao.session.state import (
    SessionRuntimeState,
    canonicalize_persisted_metadata,
    flatten_persisted_metadata,
    merge_runtime_metadata,
    normalize_runtime_metadata,
    split_runtime_metadata,
)
from ._manager_models import (
    _DISPLAY_TAIL_CACHE_LIMIT,
    _DISPLAY_TAIL_SESSION_CACHE_LIMIT,
    DisplayTailSnapshot,
    escape_sql_value,
    Session,
    SessionChangeEvent,
)


class SessionManagerBase:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self._db = None
        self._meta_tbl = None
        self._msg_tbl = None
        self._display_tail_tbl = None
        self._cache: dict[str, Session] = {}
        self._display_tail_cache: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self._active_cache: dict[str, str] = {}
        self._runtime_metadata: dict[str, SessionRuntimeState] = {}
        self._meta_lock = threading.RLock()
        self._init_lock = threading.RLock()
        self._session_locks_lock = threading.Lock()
        self._session_locks: dict[str, threading.RLock] = {}
        self._change_listeners: list[Callable[[SessionChangeEvent], None]] = []

    def _lock_for(self, key: str) -> threading.RLock:
        with self._session_locks_lock:
            lock = self._session_locks.get(key)
            if lock is None:
                lock = threading.RLock()
                self._session_locks[key] = lock
            return lock

    def _emit_change(self, event: SessionChangeEvent) -> None:
        for listener in tuple(self._change_listeners):
            try:
                listener(event)
            except Exception as exc:
                logger.warning("⚠️ session change listener failed: {} — {}", event.session_key, exc)

    @staticmethod
    def _message_storage_payload(msg: dict[str, Any]) -> dict[str, Any]:
        extra = {key: value for key, value in msg.items() if key not in ("role", "content", "timestamp")}
        return {
            "role": msg["role"],
            "content": msg.get("content", ""),
            "timestamp": msg.get("timestamp", ""),
            "extra_json": json.dumps(extra, ensure_ascii=False) if extra else "{}",
        }

    @staticmethod
    def _message_storage_payload_from_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "role": row.get("role", "user"),
            "content": row.get("content", ""),
            "timestamp": row.get("timestamp", ""),
            "extra_json": row.get("extra_json") or "{}",
        }

    @classmethod
    def _message_fingerprint(cls, msg: dict[str, Any]) -> str:
        payload = cls._message_storage_payload(msg)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return blake2b(encoded, digest_size=16).hexdigest()

    @classmethod
    def _message_fingerprint_from_row(cls, row: dict[str, Any]) -> str:
        payload = cls._message_storage_payload_from_row(row)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return blake2b(encoded, digest_size=16).hexdigest()

    @classmethod
    def _message_fingerprints(cls, messages: list[dict[str, Any]]) -> list[str]:
        return [cls._message_fingerprint(msg) for msg in messages]

    @staticmethod
    def _get_persisted_message_fingerprints(session: Session) -> list[str] | None:
        fingerprints = getattr(session, "_persisted_message_fingerprints", None)
        if isinstance(fingerprints, list):
            return [str(item) for item in fingerprints]
        return None

    @staticmethod
    def _set_persisted_message_fingerprints(session: Session, fingerprints: list[str]) -> None:
        setattr(session, "_persisted_message_fingerprints", list(fingerprints))

    def _display_tail_from_session(self, session: Session) -> list[dict[str, Any]]:
        return session.get_display_history(max_messages=_DISPLAY_TAIL_CACHE_LIMIT)

    def _store_display_tail_cache(self, key: str, messages: list[dict[str, Any]]) -> None:
        self._display_tail_cache[key] = [dict(message) for message in messages[-_DISPLAY_TAIL_CACHE_LIMIT:]]
        self._display_tail_cache.move_to_end(key)
        while len(self._display_tail_cache) > _DISPLAY_TAIL_SESSION_CACHE_LIMIT:
            self._display_tail_cache.popitem(last=False)

    def _replace_runtime_metadata(self, key: str, runtime_updates: dict[str, Any] | SessionRuntimeState) -> None:
        normalized = normalize_runtime_metadata(runtime_updates)
        if normalized.to_metadata():
            self._runtime_metadata[key] = normalized
        else:
            self._runtime_metadata.pop(key, None)

    def _merge_runtime_metadata(self, key: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return merge_runtime_metadata(metadata, self._runtime_metadata.get(key))

    def _runtime_state_for_key(self, key: str) -> SessionRuntimeState:
        runtime = self._runtime_metadata.get(key)
        if runtime is not None:
            return runtime
        session = self._cache.get(key)
        return normalize_runtime_metadata(session.metadata) if session is not None else SessionRuntimeState()

    def _refresh_cached_session_metadata(self, key: str) -> None:
        session = self._cache.get(key)
        if session is None:
            return
        persisted, _ = split_runtime_metadata(session.metadata)
        session.metadata = self._merge_runtime_metadata(key, persisted)

    def _load_persisted_metadata(self, metadata_json: str | None) -> dict[str, Any]:
        persisted, _ = split_runtime_metadata(json.loads(metadata_json or "{}"))
        return flatten_persisted_metadata(persisted)

    def _load_canonical_persisted_metadata(self, metadata_json: str | None) -> dict[str, Any]:
        persisted, _ = split_runtime_metadata(json.loads(metadata_json or "{}"))
        return canonicalize_persisted_metadata(persisted)

    def _clear_session_runtime_state(self, key: str) -> None:
        self._cache.pop(key, None)
        self._display_tail_cache.pop(key, None)
        self._runtime_metadata.pop(key, None)

    def _meta_updated_at(self, key: str) -> str:
        rows = self._meta_table().search().where(f"session_key = '{escape_sql_value(key)}'").limit(1).to_list()
        return str(rows[0].get("updated_at") or "") if rows else ""

    @staticmethod
    def _coerce_message_count(value: Any) -> int | None:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, float):
            return max(0, int(value))
        if isinstance(value, str) and value.strip().isdigit():
            return max(0, int(value.strip()))
        return None

    def _read_display_tail_row(self, key: str) -> DisplayTailSnapshot | None:
        safe = escape_sql_value(key)
        rows = self._display_tail_table().search().where(f"session_key = '{safe}'").limit(1).to_list()
        if not rows:
            return None
        return self._decode_display_tail_row(rows[0])

    def _decode_display_tail_row(self, row: dict[str, Any]) -> DisplayTailSnapshot | None:
        tail_json = row.get("tail_json") or "[]"
        try:
            payload = json.loads(tail_json)
        except Exception:
            return None
        if not isinstance(payload, list):
            return None
        messages = [dict(item) for item in payload if isinstance(item, dict)]
        return DisplayTailSnapshot(
            updated_at=str(row.get("updated_at") or ""),
            messages=messages,
            message_count=self._coerce_message_count(row.get("message_count")),
        )

    def _read_display_tail_snapshots(self) -> dict[str, DisplayTailSnapshot]:
        try:
            rows = self._display_tail_table().search().where("session_key != '_init_'").to_list()
        except Exception:
            return {}
        snapshots: dict[str, DisplayTailSnapshot] = {}
        for row in rows:
            key = str(row.get("session_key") or "")
            snapshot = self._decode_display_tail_row(row) if key else None
            if snapshot is not None:
                snapshots[key] = snapshot
        return snapshots

    def _write_display_tail_row(self, key: str, snapshot: DisplayTailSnapshot) -> None:
        table = self._display_tail_table()
        table.delete(f"session_key = '{escape_sql_value(key)}'")
        table.add(
            [{
                "session_key": key,
                "updated_at": snapshot.updated_at,
                "tail_json": json.dumps(snapshot.messages, ensure_ascii=False),
                "message_count": max(0, int(snapshot.message_count or 0)),
            }]
        )

    def _delete_display_tail_row(self, key: str) -> None:
        self._display_tail_table().delete(f"session_key = '{escape_sql_value(key)}'")

    @staticmethod
    def _best_effort_delete(table: Any, where_clause: str) -> None:
        try:
            table.delete(where_clause)
        except Exception:
            pass

    @staticmethod
    def _best_effort_add(table: Any, rows: list[dict[str, Any]]) -> None:
        if rows:
            try:
                table.add(rows)
            except Exception:
                pass
