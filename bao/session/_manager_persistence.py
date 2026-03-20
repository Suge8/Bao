from __future__ import annotations

import json
from datetime import datetime

from loguru import logger

from bao.session.state import (
    SessionActivityEvent,
    SESSION_ACTIVITY_SESSION_FINISHED,
    apply_runtime_activity,
    canonicalize_persisted_metadata,
    filter_persisted_metadata_updates,
    nest_flat_persisted_metadata,
)

from ._manager_models import escape_sql_value, Session, SessionChangeEvent
from ._manager_models import synchronized


class SessionManagerPersistenceMixin:
    def get_or_create(self, key: str) -> Session:
        with self._lock_for(key):
            if key in self._cache:
                return self._cache[key]
            session = self._load(key)
            if session is None:
                session = Session(key=key)
                self._set_persisted_message_fingerprints(session, [])
            self._cache[key] = session
            return session

    @synchronized
    def ensure_session_meta(self, key: str) -> None:
        safe = escape_sql_value(key)
        meta_tbl = self._meta_table()
        try:
            rows = meta_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
            if rows:
                return
        except Exception:
            self.save(self.get_or_create(key))
            return
        now = datetime.now()
        session = Session(key=key, created_at=now, updated_at=now)
        self._set_persisted_message_fingerprints(session, [])
        try:
            meta_tbl.add([{
                "session_key": key,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "metadata_json": json.dumps(canonicalize_persisted_metadata({}), ensure_ascii=False),
                "last_consolidated": 0,
            }])
        except Exception:
            self.save(session)
            return
        self._cache[key] = session

    def session_exists(self, key: str) -> bool:
        with self._lock_for(key):
            return key in self._cache or self._load(key) is not None

    def _load(self, key: str) -> Session | None:
        safe = escape_sql_value(key)
        with self._lock_for(key):
            try:
                meta_rows = self._meta_table().search().where(f"session_key = '{safe}'").limit(1).to_list()
                if not meta_rows:
                    return None
                meta = meta_rows[0]
                msg_rows = self._msg_table().search().where(f"session_key = '{safe}'").to_list()
                msg_rows.sort(key=lambda row: row["idx"])
                messages = self._decode_message_rows(msg_rows)
                session = Session(
                    key=key,
                    messages=messages,
                    created_at=datetime.fromisoformat(meta["created_at"]) if meta.get("created_at") else datetime.now(),
                    updated_at=datetime.fromisoformat(meta["updated_at"]) if meta.get("updated_at") else datetime.now(),
                    metadata=self._merge_runtime_metadata(key, self._load_persisted_metadata(meta.get("metadata_json"))),
                    last_consolidated=meta.get("last_consolidated", 0),
                )
                fingerprints = [self._message_fingerprint_from_row(row) for row in msg_rows]
                self._set_persisted_message_fingerprints(session, fingerprints)
                return session
            except Exception as exc:
                logger.warning("⚠️ 会话加载失败 / load failed: {} — {}", key, exc)
                return None

    @synchronized
    def update_metadata_only(self, key: str, metadata_updates: dict[str, Any], *, emit_change: bool = True) -> None:
        persisted_updates = filter_persisted_metadata_updates(metadata_updates)
        if not persisted_updates:
            return
        safe = escape_sql_value(key)
        meta_tbl = self._meta_table()
        try:
            rows = meta_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
            if not rows:
                return
            meta = rows[0]
            current_metadata = self._load_persisted_metadata(meta.get("metadata_json"))
            current_metadata.update(persisted_updates)
            meta_tbl.delete(f"session_key = '{safe}'")
            meta_tbl.add([{
                "session_key": key,
                "created_at": meta["created_at"],
                "updated_at": meta["updated_at"],
                "metadata_json": json.dumps(nest_flat_persisted_metadata(current_metadata), ensure_ascii=False),
                "last_consolidated": meta.get("last_consolidated", 0),
            }])
            if key in self._cache:
                self._cache[key].metadata.update(persisted_updates)
                self._refresh_cached_session_metadata(key)
            if emit_change:
                self._emit_change(SessionChangeEvent(session_key=key, kind="metadata"))
        except Exception as exc:
            logger.warning("⚠️ metadata update failed: {} — {}", key, exc)

    @synchronized
    def apply_session_activity(self, key: str, activity: SessionActivityEvent, *, emit_change: bool = True) -> None:
        next_runtime = apply_runtime_activity(self._runtime_state_for_key(key), activity)
        self._replace_runtime_metadata(key, next_runtime)
        self._refresh_cached_session_metadata(key)
        if emit_change:
            self._emit_change(SessionChangeEvent(session_key=key, kind="metadata"))

    @synchronized
    def mark_desktop_turn_completed(
        self,
        session_key: str,
        *,
        emit_change: bool = True,
        metadata_updates: dict[str, Any] | None = None,
    ) -> None:
        if not session_key:
            return
        self.apply_session_activity(session_key, SessionActivityEvent(kind=SESSION_ACTIVITY_SESSION_FINISHED), emit_change=False)
        payload = {"desktop_last_seen_ai_at": datetime.now().isoformat()}
        if isinstance(metadata_updates, dict):
            payload.update(filter_persisted_metadata_updates(metadata_updates))
        self.update_metadata_only(session_key, payload, emit_change=False)
        if emit_change:
            self._emit_change(SessionChangeEvent(session_key=session_key, kind="metadata"))
