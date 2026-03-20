from __future__ import annotations

import json
from typing import Any

from loguru import logger

from bao.session.state import build_session_snapshot, session_routing_metadata

from ._manager_models import (
    _DISPLAY_TAIL_CACHE_LIMIT,
    _RUNTIME_CONTEXT_TAG,
    DisplayTailSnapshot,
    escape_sql_value,
    synchronized,
)


class SessionManagerDisplayMixin:
    @staticmethod
    def _display_entry_from_message(message: dict[str, Any]) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "role": message.get("role", "user"),
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

    @classmethod
    def _decode_cached_messages(
        cls,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            cls._display_entry_from_message(message)
            for message in messages
            if not (
                message.get("role") == "user"
                and isinstance(message.get("content"), str)
                and str(message.get("content")).startswith(_RUNTIME_CONTEXT_TAG)
            )
        ]

    @staticmethod
    def _decode_message_rows(msg_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for row in msg_rows:
            message: dict[str, Any] = {
                "role": row["role"],
                "content": row["content"],
                "timestamp": row["timestamp"],
            }
            extra_json = row.get("extra_json") or "{}"
            if extra_json != "{}":
                message.update(json.loads(extra_json))
            messages.append(message)
        return [
            dict(message)
            for message in messages
            if not (
                message.get("role") == "user"
                and isinstance(message.get("content"), str)
                and str(message.get("content")).startswith(_RUNTIME_CONTEXT_TAG)
            )
        ]

    def _session_message_summary(
        self,
        key: str,
        updated_at: str,
        persisted: DisplayTailSnapshot | None = None,
    ) -> tuple[int | None, bool | None, bool]:
        cached = self._cache.get(key)
        if cached is not None:
            count = len(cached.messages)
            return count, count > 0, False
        persisted = persisted or self._read_display_tail_row(key)
        if persisted is None or persisted.updated_at != updated_at:
            return None, None, bool(updated_at)
        count = persisted.message_count if persisted.message_count is not None else len(persisted.messages)
        return count, count > 0, False

    def _build_session_list_entry(
        self,
        row: dict[str, Any],
        *,
        persisted: DisplayTailSnapshot | None = None,
    ) -> dict[str, Any]:
        key = str(row.get("session_key") or "")
        updated_at = str(row.get("updated_at") or "")
        message_count, has_messages, needs_tail_backfill = self._session_message_summary(
            key,
            updated_at,
            persisted=persisted,
        )
        persisted_metadata = self._load_canonical_persisted_metadata(row.get("metadata_json"))
        merged_metadata = self._merge_runtime_metadata(key, persisted_metadata)
        snapshot = build_session_snapshot(persisted_metadata, runtime_updates=self._runtime_metadata.get(key))
        return {
            "key": key,
            "created_at": row.get("created_at"),
            "updated_at": updated_at,
            "metadata": merged_metadata,
            "routing": snapshot.routing.as_snapshot(),
            "runtime": snapshot.runtime.as_snapshot(),
            "workflow": snapshot.workflow.as_snapshot(),
            "view": snapshot.view.as_snapshot(),
            "message_count": message_count,
            "has_messages": has_messages,
            "needs_tail_backfill": needs_tail_backfill,
        }

    def peek_tail_messages(self, key: str, limit: int) -> list[dict[str, Any]] | None:
        max_messages = limit if limit > 0 else _DISPLAY_TAIL_CACHE_LIMIT
        lock = self._lock_for(key)
        if not lock.acquire(blocking=False):
            return None
        try:
            cached = self._cache.get(key)
            if cached is not None:
                return cached.get_display_history(max_messages=max_messages)
            cached_tail = self._display_tail_cache.get(key)
            if cached_tail is None:
                return None
            self._display_tail_cache.move_to_end(key)
            if limit > 0:
                cached_tail = cached_tail[-limit:]
            return [dict(message) for message in cached_tail]
        finally:
            lock.release()

    def get_tail_messages(self, key: str, limit: int) -> list[dict[str, Any]]:
        cached_messages = self.peek_tail_messages(key, limit)
        if cached_messages is not None:
            return cached_messages
        safe = escape_sql_value(key)
        where_clause = f"session_key = '{safe}'"
        msg_tbl: Any = self._msg_table()
        with self._lock_for(key):
            try:
                current_updated_at = self._meta_updated_at(key)
                persisted = self._read_display_tail_row(key)
                if persisted is not None and persisted.updated_at == current_updated_at:
                    self._store_display_tail_cache(key, persisted.messages)
                    messages = persisted.messages[-limit:] if limit > 0 else persisted.messages
                    return [dict(message) for message in messages]
                total = msg_tbl.count_rows(filter=where_clause) if limit > 0 else 0
                if limit > 0 and total <= 0:
                    if current_updated_at:
                        self._write_display_tail_row(
                            key,
                            DisplayTailSnapshot(updated_at=current_updated_at, messages=[], message_count=0),
                        )
                        self._store_display_tail_cache(key, [])
                    return []
                search_clause = where_clause if limit <= 0 else f"{where_clause} AND idx >= {max(total - limit, 0)}"
                msg_rows = msg_tbl.search().where(search_clause).to_list()
                if not msg_rows:
                    if current_updated_at:
                        self._write_display_tail_row(
                            key,
                            DisplayTailSnapshot(updated_at=current_updated_at, messages=[], message_count=0),
                        )
                        self._store_display_tail_cache(key, [])
                    return []
                msg_rows.sort(key=lambda row: row["idx"])
                trimmed_rows = msg_rows[-limit:] if limit > 0 else msg_rows
                messages = self._decode_message_rows(trimmed_rows)
                if limit <= 0 or limit >= _DISPLAY_TAIL_CACHE_LIMIT:
                    self._store_display_tail_cache(key, messages)
                    if current_updated_at:
                        count = total if limit > 0 else len(messages)
                        self._write_display_tail_row(
                            key,
                            DisplayTailSnapshot(
                                updated_at=current_updated_at,
                                messages=messages,
                                message_count=count,
                            ),
                        )
                return messages
            except Exception as exc:
                logger.warning("⚠️ get_tail_messages failed: {} — {}", key, exc)
                return []

    def get_display_messages(self, key: str) -> list[dict[str, Any]]:
        session = self._cache.get(key)
        if session is not None:
            return self._decode_cached_messages(session.messages[session.last_consolidated :])
        safe = escape_sql_value(key)
        with self._lock_for(key):
            session = self._cache.get(key)
            if session is not None:
                return self._decode_cached_messages(session.messages[session.last_consolidated :])
            try:
                msg_rows = self._msg_table().search().where(f"session_key = '{safe}'").to_list()
            except Exception as exc:
                logger.warning("⚠️ get_display_messages failed: {} — {}", key, exc)
                return []
            msg_rows.sort(key=lambda row: row["idx"])
            return self._decode_message_rows(msg_rows)

    def backfill_display_tail_rows(self, keys: list[str], limit: int) -> None:
        seen: set[str] = set()
        for raw_key in keys:
            key = str(raw_key).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            current_updated_at = self._meta_updated_at(key)
            persisted = self._read_display_tail_row(key) if current_updated_at else None
            if current_updated_at and (persisted is None or persisted.updated_at != current_updated_at):
                self.get_tail_messages(key, limit)

    def list_child_sessions(self, parent_session_key: str) -> list[dict[str, Any]]:
        if not isinstance(parent_session_key, str) or not parent_session_key:
            return []
        children: list[dict[str, Any]] = []
        for session in self.list_sessions():
            metadata = session.get("metadata")
            if isinstance(metadata, dict) and session_routing_metadata(metadata).parent_session_key == parent_session_key:
                children.append(session)
        return children

    @synchronized
    def list_sessions(self) -> list[dict[str, Any]]:
        session_rows, _active_key = self._list_session_rows_with_active_key("")
        return self._build_session_list_entries(session_rows)

    @synchronized
    def list_sessions_with_active_key(self, natural_key: str) -> tuple[list[dict[str, Any]], str]:
        session_rows, active_key = self._list_session_rows_with_active_key(natural_key)
        return self._build_session_list_entries(session_rows), active_key

    def _list_session_rows_with_active_key(self, natural_key: str) -> tuple[list[dict[str, Any]], str]:
        try:
            rows = self._meta_table().search().where("session_key != '_init_'").to_list()
        except Exception:
            return [], ""
        normalized_key = str(natural_key or "").strip()
        return self._partition_session_rows(rows, normalized_key)

    @synchronized
    def get_session_list_entry(self, key: str) -> dict[str, Any] | None:
        rows = self._meta_table().search().where(f"session_key = '{escape_sql_value(key)}'").limit(1).to_list()
        return self._build_session_list_entry(rows[0]) if rows else None

    def _build_session_list_entries(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        session_rows = [row for row in rows if not str(row.get("session_key") or "").startswith("_active:")]
        if not session_rows:
            return []
        tail_snapshots = self._read_display_tail_snapshots()
        sessions = [
            self._build_session_list_entry(row, persisted=tail_snapshots.get(str(row.get("session_key") or "")))
            for row in session_rows
        ]
        return sorted(sessions, key=lambda session: session.get("updated_at", ""), reverse=True)

    def _partition_session_rows(
        self,
        rows: list[dict[str, Any]],
        natural_key: str,
    ) -> tuple[list[dict[str, Any]], str]:
        marker_key = f"_active:{natural_key}" if natural_key else ""
        active_key = self._active_cache.get(natural_key, "") if natural_key else ""
        latest_marker_row: dict[str, Any] | None = None
        latest_marker_updated_at = ""
        session_rows: list[dict[str, Any]] = []
        for row in rows:
            session_key = str(row.get("session_key") or "")
            if session_key.startswith("_active:"):
                if (
                    marker_key
                    and not active_key
                    and session_key == marker_key
                    and str(row.get("updated_at") or "") >= latest_marker_updated_at
                ):
                    latest_marker_row = row
                    latest_marker_updated_at = str(row.get("updated_at") or "")
                continue
            session_rows.append(row)
        if not natural_key:
            return session_rows, ""
        if active_key:
            return session_rows, active_key
        resolved_active_key = self._active_key_from_row(latest_marker_row, natural_key)
        return session_rows, resolved_active_key

    def _active_key_from_row(self, row: dict[str, Any] | None, natural_key: str) -> str:
        if not natural_key or row is None:
            self._active_cache.pop(natural_key, None)
            return ""
        try:
            value = json.loads(row.get("metadata_json") or "{}").get("active_key")
        except Exception:
            self._active_cache.pop(natural_key, None)
            return ""
        if not value:
            self._active_cache.pop(natural_key, None)
            return ""
        normalized = str(value)
        self._active_cache[natural_key] = normalized
        return normalized

    def list_sessions_for(self, natural_key: str) -> list[dict[str, Any]]:
        prefix = f"{natural_key}::"
        return [item for item in self.list_sessions() if item["key"] == natural_key or item["key"].startswith(prefix)]
