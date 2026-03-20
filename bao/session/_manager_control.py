from __future__ import annotations

import json
from datetime import datetime

from bao.session._tree import collect_session_tree_keys
from bao.session.state import (
    SESSION_ACTIVITY_CHILD_CLEARED,
    SESSION_ACTIVITY_CHILD_STARTED,
    SESSION_ACTIVITY_SESSION_FINISHED,
    SESSION_ACTIVITY_SESSION_STARTED,
    SessionActivityEvent,
)

from ._manager_models import (
    MarkDesktopSeenRequest,
    SessionChangeEvent,
    escape_sql_value,
    synchronized,
)


class SessionManagerControlMixin:
    @synchronized
    def close(self) -> None:
        self._cache.clear()
        self._display_tail_cache.clear()
        self._active_cache.clear()
        self._runtime_metadata.clear()
        self._change_listeners.clear()
        self._session_locks.clear()
        self._meta_tbl = None
        self._msg_tbl = None
        self._display_tail_tbl = None
        self._db = None

    @synchronized
    def add_change_listener(self, listener) -> None:
        if listener not in self._change_listeners:
            self._change_listeners.append(listener)

    @synchronized
    def remove_change_listener(self, listener) -> None:
        if listener in self._change_listeners:
            self._change_listeners.remove(listener)

    @synchronized
    def set_session_running(self, key: str, is_running: bool, *, emit_change: bool = True) -> None:
        kind = SESSION_ACTIVITY_SESSION_STARTED if bool(is_running) else SESSION_ACTIVITY_SESSION_FINISHED
        self.apply_session_activity(key, SessionActivityEvent(kind=kind), emit_change=emit_change)

    @synchronized
    def set_child_running(self, key: str, task_id: str, *, emit_change: bool = True) -> None:
        self.apply_session_activity(
            key,
            SessionActivityEvent(kind=SESSION_ACTIVITY_CHILD_STARTED, task_id=str(task_id or "")),
            emit_change=emit_change,
        )

    @synchronized
    def clear_child_running(self, key: str, *, emit_change: bool = True) -> None:
        self.apply_session_activity(key, SessionActivityEvent(kind=SESSION_ACTIVITY_CHILD_CLEARED), emit_change=emit_change)

    @synchronized
    def invalidate(self, key: str) -> None:
        self._clear_session_runtime_state(key)

    @synchronized
    def _delete_meta_row(self, key: str) -> bool:
        try:
            self._meta_table().delete(f"session_key = '{escape_sql_value(key)}'")
            return True
        except Exception:
            return False

    @synchronized
    def delete_session(self, key: str) -> bool:
        safe = escape_sql_value(key)
        meta_tbl = self._meta_table()
        msg_tbl = self._msg_table()
        tail_tbl = self._display_tail_table()
        try:
            prev_meta = meta_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
        except Exception:
            prev_meta = []
        try:
            prev_msgs = msg_tbl.search().where(f"session_key = '{safe}'").to_list()
        except Exception:
            prev_msgs = []
        try:
            prev_tail = tail_tbl.search().where(f"session_key = '{safe}'").limit(1).to_list()
        except Exception:
            prev_tail = []
        ok = self._delete_meta_row(key)
        try:
            msg_tbl.delete(f"session_key = '{safe}'")
        except Exception:
            ok = False
        try:
            self._delete_display_tail_row(key)
        except Exception:
            ok = False
        if not ok:
            self._best_effort_delete(meta_tbl, f"session_key = '{safe}'")
            self._best_effort_delete(msg_tbl, f"session_key = '{safe}'")
            self._best_effort_add(meta_tbl, prev_meta)
            self._best_effort_add(msg_tbl, prev_msgs)
            self._best_effort_add(tail_tbl, prev_tail)
            self._clear_session_runtime_state(key)
            return False
        self._clear_session_runtime_state(key)
        for natural_key, active_key in list(self._active_cache.items()):
            if active_key == key:
                self._active_cache.pop(natural_key, None)
        try:
            rows = meta_tbl.search().where("session_key != '_init_'").to_list()
            for row in rows:
                session_key = str(row.get("session_key", ""))
                if not session_key.startswith("_active:"):
                    continue
                natural_key = session_key[len("_active:") :]
                active_key = json.loads(row.get("metadata_json") or "{}").get("active_key")
                if active_key == key:
                    ok = self._delete_meta_row(session_key) and ok
                    self._active_cache.pop(natural_key, None)
        except Exception:
            ok = False
        try:
            from bao.agent.artifacts import ArtifactStore

            ArtifactStore(self.workspace, key, 0).cleanup_session()
        except Exception:
            pass
        self._emit_change(SessionChangeEvent(session_key=key, kind="deleted"))
        return ok

    @synchronized
    def delete_session_tree(self, key: str) -> bool:
        """递归删除 session 及其所有后代节点。"""
        to_delete = collect_session_tree_keys(key, self._child_session_keys)
        ok = True
        for session_key in reversed(to_delete):
            ok = self.delete_session(session_key) and ok
        return ok

    def _child_session_keys(self, parent_session_key: str) -> tuple[str, ...]:
        child_keys: list[str] = []
        for child_item in self.list_child_sessions(parent_session_key):
            child_key = str(child_item.get("key", "")).strip()
            if child_key:
                child_keys.append(child_key)
        return tuple(child_keys)

    @synchronized
    def get_active_session_key(self, natural_key: str) -> str | None:
        if natural_key in self._active_cache:
            return self._active_cache[natural_key]
        safe = escape_sql_value(f"_active:{natural_key}")
        try:
            rows = self._meta_table().search().where(f"session_key = '{safe}'").to_list()
            rows.sort(key=lambda row: str(row.get("updated_at", "")), reverse=True)
            for row in rows:
                try:
                    value = json.loads(row.get("metadata_json") or "{}").get("active_key")
                except Exception:
                    continue
                if value:
                    self._active_cache[natural_key] = value
                    return value
        except Exception:
            pass
        return None

    @synchronized
    def resolve_active_session_key(self, natural_key: str) -> str:
        active_key = self.get_active_session_key(natural_key)
        if isinstance(active_key, str) and active_key:
            if (active_key == natural_key or active_key.startswith(f"{natural_key}::")) and self.session_exists(active_key):
                return active_key
        return natural_key

    @synchronized
    def mark_desktop_seen_ai(
        self,
        session_key: str,
        request: MarkDesktopSeenRequest | None = None,
    ) -> None:
        if not session_key:
            return
        request = request or MarkDesktopSeenRequest()
        if request.clear_running:
            self.mark_desktop_turn_completed(
                session_key,
                emit_change=request.emit_change,
                metadata_updates=request.metadata_updates,
            )
            return
        payload = {"desktop_last_seen_ai_at": datetime.now().isoformat()}
        if isinstance(request.metadata_updates, dict):
            from bao.session.state import filter_persisted_metadata_updates

            payload.update(filter_persisted_metadata_updates(request.metadata_updates))
        self.update_metadata_only(session_key, payload, emit_change=False)
        if request.emit_change:
            self._emit_change(SessionChangeEvent(session_key=session_key, kind="metadata"))

    @synchronized
    def mark_desktop_seen_ai_if_active(self, session_key: str, desktop_natural_key: str = "desktop:local") -> None:
        if session_key and self.get_active_session_key(desktop_natural_key) == session_key:
            self.mark_desktop_seen_ai(session_key, MarkDesktopSeenRequest(emit_change=False))

    @synchronized
    def set_active_session_key(self, natural_key: str, session_key: str) -> None:
        self._active_cache[natural_key] = session_key
        marker = f"_active:{natural_key}"
        self._delete_meta_row(marker)
        now = datetime.now().isoformat()
        self._meta_table().add([{
            "session_key": marker,
            "created_at": now,
            "updated_at": now,
            "metadata_json": json.dumps({"active_key": session_key}, ensure_ascii=False),
            "last_consolidated": 0,
        }])

    @synchronized
    def clear_active_session_key(self, natural_key: str) -> None:
        self._active_cache.pop(natural_key, None)
        self._delete_meta_row(f"_active:{natural_key}")
