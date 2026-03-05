"""SessionService — wraps Bao SessionManager for the desktop channel.

All SessionManager calls are dispatched to the asyncio thread via AsyncioRunner.
Internal signals marshal results back to the Qt main thread.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from typing import Any

from loguru import logger
from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)

from app.backend.asyncio_runner import AsyncioRunner

_DEBUG_SWITCH = os.getenv("BAO_DESKTOP_DEBUG_SWITCH") == "1"

_ROLE_BASE = int(Qt.ItemDataRole.UserRole)
_ROLE_KEY = _ROLE_BASE + 1
_ROLE_TITLE = _ROLE_BASE + 2
_ROLE_IS_ACTIVE = _ROLE_BASE + 3
_ROLE_UPDATED_AT = _ROLE_BASE + 4
_ROLE_CHANNEL = _ROLE_BASE + 5
_ROLE_HAS_UNREAD = _ROLE_BASE + 6


def _format_display_title(key: str, title: Any, *, natural_key: str = "desktop:local") -> str:
    if isinstance(title, str):
        cleaned = title.strip()
        if cleaned:
            return cleaned

    if key == natural_key:
        return "default"

    if "::" in key:
        _prefix, _sep, suffix = key.partition("::")
        if suffix:
            return suffix

    return key


class SessionListModel(QAbstractListModel):
    """Simple list model exposing session dicts to QML."""

    _ROLES = {
        _ROLE_KEY: QByteArray(b"key"),
        _ROLE_TITLE: QByteArray(b"title"),
        _ROLE_IS_ACTIVE: QByteArray(b"isActive"),
        _ROLE_UPDATED_AT: QByteArray(b"updatedAt"),
        _ROLE_CHANNEL: QByteArray(b"channel"),
        _ROLE_HAS_UNREAD: QByteArray(b"hasUnread"),
    }

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._sessions: list[dict[str, Any]] = []
        self._active_key: str = ""

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._sessions)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._sessions)):
            return None
        s = self._sessions[index.row()]
        if role == _ROLE_KEY:
            return s.get("key", "")
        if role == _ROLE_TITLE:
            key = str(s.get("key", ""))
            return _format_display_title(key, s.get("title"))
        if role == _ROLE_IS_ACTIVE:
            return s.get("key", "") == self._active_key
        if role == _ROLE_UPDATED_AT:
            return s.get("updated_at", 0)
        if role == _ROLE_CHANNEL:
            return s.get("channel", "other")
        if role == _ROLE_HAS_UNREAD:
            return bool(s.get("has_unread", False))
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return dict(self._ROLES)

    def reset_sessions(
        self,
        sessions: list[dict[str, Any]],
        active_key: str,
    ) -> None:
        self.beginResetModel()
        self._sessions = sessions
        self._active_key = active_key
        self.endResetModel()

    def set_active(self, key: str) -> None:
        if self._active_key == key:
            return
        old_key = self._active_key
        self._active_key = key
        for i, s in enumerate(self._sessions):
            if s.get("key") in (old_key, key):
                idx = self.index(i)
                self.dataChanged.emit(idx, idx, [_ROLE_IS_ACTIVE])


class SessionService(QObject):
    sessionsChanged = Signal()
    activeKeyChanged = Signal(str)
    activeReady = Signal(str)
    errorOccurred = Signal(str)
    deleteCompleted = Signal(str, bool, str)

    # Internal signals: asyncio thread → Qt main thread
    _listResult = Signal(bool, str, object)  # ok, error, (sessions, active)
    _selectResult = Signal(bool, str, str)  # ok, error, key
    _createResult = Signal(bool, str, str)  # ok, error, key
    _deleteResult = Signal(str, bool, str)

    def __init__(self, runner: AsyncioRunner, parent: Any = None) -> None:
        super().__init__(parent)
        self._runner = runner
        self._session_manager: Any = None
        self._natural_key = "desktop:local"
        self._gateway_ready = False
        self._active_key = ""
        self._pending_select_key: str | None = None
        self._last_emitted_active_key = ""
        self._model = SessionListModel()
        self._pending_deletes: dict[str, tuple[list[dict[str, Any]], str, str]] = {}
        self._pending_creates: set[str] = set()
        self._list_fp: tuple[tuple[Any, ...], ...] | None = None
        self._list_request_seq = 0
        self._list_latest_seq = 0
        self._disposed = False

        self._listResult.connect(self._handle_list_result)
        self._selectResult.connect(self._handle_select_result)
        self._createResult.connect(self._handle_create_result)
        self._deleteResult.connect(self._handle_delete_result)

    @Property(QObject, constant=True)
    def sessionsModel(self) -> SessionListModel:
        return self._model

    @Property(str, notify=activeKeyChanged)
    def activeKey(self) -> str:
        return self._active_key

    def initialize(self, session_manager: Any) -> None:
        """Called after ChatService has initialized the Bao SessionManager."""
        if self._disposed:
            return
        self._session_manager = session_manager
        self.refresh()

    @Slot()
    def shutdown(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._pending_select_key = None
        self._pending_deletes.clear()
        self._pending_creates.clear()
        self._session_manager = None

    def _submit_safe(self, coro: Coroutine[Any, Any, Any]) -> Any:
        try:
            return self._runner.submit(coro)
        except RuntimeError:
            coro.close()
            return None

    async def _run_user_io(self, fn: Any, *args: Any) -> Any:
        if isinstance(self._runner, AsyncioRunner):
            return await self._runner.run_user_io(fn, *args)
        return await asyncio.to_thread(fn, *args)

    def _emit_active_key_if_changed(self, new_key: str) -> None:
        """Emit activeKeyChanged only if key actually changed."""
        if new_key != self._last_emitted_active_key:
            self._last_emitted_active_key = new_key
            self.activeKeyChanged.emit(new_key)
            self._emit_active_ready_if_applicable(new_key)

    def _emit_active_ready_if_applicable(self, key: str) -> None:
        if self._gateway_ready and key:
            self.activeReady.emit(key)

    @staticmethod
    def _pick_latest_key(sessions: list[dict[str, Any]], *, preferred_channel: str) -> str:
        def _updated_at_sort_value(item: dict[str, Any]) -> tuple[int, float | str]:
            v = item.get("updated_at", "")
            if isinstance(v, (int, float)):
                return (2, float(v))
            if isinstance(v, str) and v:
                return (1, v)
            return (0, "")

        def _key_value(item: dict[str, Any]) -> str:
            v = item.get("key", "")
            return str(v) if v is not None else ""

        preferred = [s for s in sessions if str(s.get("channel", "")) == preferred_channel]
        candidates = preferred if preferred else sessions
        if not candidates:
            return ""
        sort_values = [_updated_at_sort_value(s) for s in candidates]
        if not any(v[0] > 0 for v in sort_values):
            return _key_value(candidates[0])
        if len(set(sort_values)) == 1:
            return _key_value(candidates[0])
        best = max(candidates, key=lambda s: (_updated_at_sort_value(s), _key_value(s)))
        return _key_value(best)

    def _clear_pending_select_if_resolved(self, active_key: str) -> None:
        if self._pending_select_key is not None and active_key == self._pending_select_key:
            self._pending_select_key = None

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        if self._disposed:
            return
        if self._session_manager is None:
            return
        self._list_request_seq += 1
        seq = self._list_request_seq
        self._list_latest_seq = seq
        fut = self._submit_safe(self._list_sessions(seq))
        if fut is None:
            return
        fut.add_done_callback(self._on_list_done)

    @Slot()
    def setGatewayReady(self) -> None:
        self._gateway_ready = True
        if self._active_key:
            self._emit_active_ready_if_applicable(self._active_key)

    @Slot(str)
    def newSession(self, name: str = "") -> None:
        if self._disposed:
            return

        if self._session_manager is None:
            return

        key = self._build_new_session_key(name)

        if any(str(s.get("key", "")) == key for s in self._model._sessions):
            self.selectSession(key)
            return

        sessions_before = [dict(s) for s in self._model._sessions]
        self._pending_creates.add(key)

        sessions_after = [
            {
                "key": key,
                "title": _format_display_title(key, None, natural_key=self._natural_key),
                "updated_at": "",
                "channel": "desktop",
                "has_unread": False,
            },
            *sessions_before,
        ]

        self._gateway_ready = True
        self._pending_select_key = key
        if self._active_key != key:
            self._active_key = key
            self._model.set_active(key)
            if _DEBUG_SWITCH:
                logger.debug("session_select_commit key={}", key)
            self._emit_active_key_if_changed(key)
        self._model.reset_sessions(sessions_after, key)
        self.sessionsChanged.emit()

        fut = self._submit_safe(self._create_session(key))
        if fut is None:
            return
        fut.add_done_callback(lambda future, k=key: self._on_create_done(k, future))

    @Slot(str)
    def selectSession(self, key: str) -> None:
        if self._disposed:
            return
        if _DEBUG_SWITCH:
            logger.debug("session_select_request key={}", key)
        if not key:
            return
        self._gateway_ready = True
        if self._pending_select_key == key:
            return
        self._pending_select_key = key
        if self._active_key != key:
            self._active_key = key
            self._model.set_active(key)
            if _DEBUG_SWITCH:
                logger.debug("session_select_commit key={}", key)
            self._emit_active_key_if_changed(key)
        fut = self._submit_safe(self._select_session(key))
        if fut is None:
            return
        fut.add_done_callback(self._on_select_done)

    @Slot(str)
    def deleteSession(self, key: str) -> None:
        if self._disposed:
            return
        if not key or self._session_manager is None or key in self._pending_deletes:
            return
        sessions_before = [dict(s) for s in self._model._sessions]
        active_before = self._active_key
        removed_index = next(
            (i for i, s in enumerate(sessions_before) if s.get("key") == key),
            -1,
        )
        sessions_after = [dict(s) for s in sessions_before if s.get("key") != key]
        if removed_index < 0 or len(sessions_after) == len(sessions_before):
            return

        new_active = active_before
        removed_channel = str(sessions_before[removed_index].get("channel") or "")
        if not sessions_after:
            new_active = self._build_new_session_key("")
            self._pending_creates.add(new_active)
            sessions_after = [
                {
                    "key": new_active,
                    "title": _format_display_title(new_active, None, natural_key=self._natural_key),
                    "updated_at": "",
                    "channel": "desktop",
                    "has_unread": False,
                }
            ]
            fut_create = self._submit_safe(self._create_session(new_active))
            if fut_create is not None:
                fut_create.add_done_callback(
                    lambda future, k=new_active: self._on_create_done(k, future)
                )
        elif active_before == key:
            new_active = self._pick_latest_key(
                sessions_after,
                preferred_channel=(removed_channel or "desktop"),
            )

        for item in sessions_after:
            if str(item.get("key", "")) == new_active:
                item["has_unread"] = False

        self._pending_deletes[key] = (sessions_before, active_before, new_active)
        self._active_key = new_active
        self._model.reset_sessions(sessions_after, new_active)
        self.sessionsChanged.emit()
        self._emit_active_key_if_changed(new_active)

        fut = self._submit_safe(self._delete_session(key, new_active))
        if fut is None:
            self._pending_deletes.pop(key, None)
            return
        fut.add_done_callback(lambda future, k=key: self._on_delete_done(k, future))

    # ------------------------------------------------------------------
    # Async helpers (run on asyncio thread)
    # ------------------------------------------------------------------

    async def _list_sessions(self, seq: int) -> tuple[int, list[dict[str, Any]], str]:
        sm = self._session_manager
        sessions = await self._run_user_io(sm.list_sessions)
        active_raw = await self._run_user_io(sm.get_active_session_key, self._natural_key)
        active = active_raw or ""
        result = []
        for s in sessions:
            key = s["key"]
            channel = key.split(":")[0] if ":" in key else (key if key == "heartbeat" else "other")
            meta = s.get("metadata", {})
            last_ai = meta.get("desktop_last_ai_at")
            last_seen_ai = meta.get("desktop_last_seen_ai_at")
            has_unread = False
            if isinstance(last_ai, str) and last_ai:
                seen_ai = (
                    last_seen_ai if isinstance(last_seen_ai, str) and last_seen_ai else last_ai
                )
                has_unread = seen_ai < last_ai
            result.append(
                {
                    "key": key,
                    "title": _format_display_title(
                        key, meta.get("title"), natural_key=self._natural_key
                    ),
                    "updated_at": s.get("updated_at", ""),
                    "channel": channel,
                    "has_unread": has_unread,
                }
            )
        return seq, result, active

    def _build_new_session_key(self, name: str) -> str:
        if name:
            return f"{self._natural_key}::{name}"
        import time

        return f"{self._natural_key}::session-{int(time.time())}"

    async def _create_session(self, key: str) -> str:
        sm = self._session_manager

        def _create() -> None:
            session = sm.get_or_create(key)
            sm.save(session)
            sm.set_active_session_key(self._natural_key, key)

        await self._run_user_io(_create)
        return key

    async def _select_session(self, key: str) -> str:
        await self._run_user_io(
            self._session_manager.set_active_session_key, self._natural_key, key
        )
        return key

    async def _delete_session(self, key: str, new_active: str) -> None:
        sm = self._session_manager

        def _delete() -> None:
            was_active = sm.get_active_session_key(self._natural_key) == key
            deleted = sm.delete_session(key)
            if not deleted:
                still_exists = True
                try:
                    still_exists = any(s.get("key") == key for s in sm.list_sessions())
                except Exception:
                    still_exists = True
                if still_exists:
                    raise RuntimeError(f"delete session failed: {key}")
            if was_active:
                if new_active:
                    sm.set_active_session_key(self._natural_key, new_active)
                else:
                    sm.clear_active_session_key(self._natural_key)

        await self._run_user_io(_delete)

    # ------------------------------------------------------------------
    # Callbacks (asyncio thread — emit signals only, no Qt ops)
    # ------------------------------------------------------------------

    def _on_list_done(self, future: Any) -> None:
        if self._disposed:
            return
        exc = future.exception()
        if exc:
            self._listResult.emit(False, str(exc), None)
        else:
            self._listResult.emit(True, "", future.result())

    def _on_select_done(self, future: Any) -> None:
        if self._disposed:
            return
        exc = future.exception()
        if exc:
            self._selectResult.emit(False, str(exc), "")
        else:
            self._selectResult.emit(True, "", future.result())

    def _on_create_done(self, key: str, future: Any) -> None:
        if self._disposed:
            return
        exc = future.exception()
        if exc:
            self._createResult.emit(False, str(exc), key)
        else:
            self._createResult.emit(True, "", str(future.result() or key))

    def _on_delete_done(self, key: str, future: Any) -> None:
        if self._disposed:
            return
        exc = future.exception()
        if exc:
            self._deleteResult.emit(key, False, str(exc))
        else:
            self._deleteResult.emit(key, True, "")

    # ------------------------------------------------------------------
    # Main-thread handlers (connected via signals)
    # ------------------------------------------------------------------

    def _handle_list_result(self, ok: bool, error: str, data: Any) -> None:
        if self._disposed:
            return
        if not ok:
            self.errorOccurred.emit(error)
            return
        seq = 0
        sessions: list[dict[str, Any]]
        if isinstance(data, tuple) and len(data) == 3 and isinstance(data[0], int):
            seq, sessions, _active = data
            if seq != self._list_latest_seq:
                return
        else:
            if not (isinstance(data, tuple) and len(data) == 2):
                return
            raw_sessions, _raw_active = data
            if not isinstance(raw_sessions, list):
                return
            sessions = [s for s in raw_sessions if isinstance(s, dict)]
        active_for_view = self._pending_select_key or self._active_key

        pending_keys = set(self._pending_deletes.keys())
        if pending_keys:
            sessions = [s for s in sessions if s.get("key") not in pending_keys]
            if active_for_view in pending_keys:
                active_for_view = ""

        pending_create_keys = set(self._pending_creates)
        if pending_create_keys:
            existing_keys = {str(s.get("key", "")) for s in sessions}
            for key in pending_create_keys:
                if key in existing_keys:
                    continue
                sessions.insert(
                    0,
                    {
                        "key": key,
                        "title": _format_display_title(key, None, natural_key=self._natural_key),
                        "updated_at": "",
                        "channel": "desktop",
                        "has_unread": False,
                    },
                )
                existing_keys.add(key)

        if self._gateway_ready and not sessions and not pending_create_keys:
            if self._session_manager is not None:
                self.newSession("")
                return

        if self._gateway_ready and not self._pending_select_key and not active_for_view:
            if sessions:
                active_for_view = self._pick_latest_key(sessions, preferred_channel="desktop")
                if active_for_view:
                    self._active_key = active_for_view
                    self._model.set_active(active_for_view)
                    self._emit_active_key_if_changed(active_for_view)
            else:
                if self._session_manager is not None:
                    self.newSession("")
                    return

        if (
            active_for_view
            and active_for_view not in pending_create_keys
            and not any(str(s.get("key", "")) == active_for_view for s in sessions)
        ):
            active_for_view = ""
        if not self._gateway_ready:
            active_for_view = ""

        if not sessions and self._active_key:
            self._active_key = ""
            self._emit_active_key_if_changed("")

        for item in sessions:
            if str(item.get("key", "")) == active_for_view:
                item["has_unread"] = False
        fp = tuple(
            (
                s["key"],
                s.get("title", ""),
                bool(s.get("has_unread", False)),
            )
            for s in sessions
        )
        if self._list_fp == fp:
            if active_for_view == self._active_key:
                self._clear_pending_select_if_resolved(active_for_view)
                return
            self._active_key = active_for_view
            self._model.set_active(active_for_view)
            self._clear_pending_select_if_resolved(active_for_view)
            return
        self._list_fp = fp
        self._active_key = active_for_view
        self._model.reset_sessions(sessions, active_for_view)
        self.sessionsChanged.emit()
        self._clear_pending_select_if_resolved(active_for_view)

    def _handle_select_result(self, ok: bool, error: str, key: str) -> None:
        if self._disposed:
            return
        if self._pending_select_key is not None and key != self._pending_select_key:
            return
        if not ok:
            self._pending_select_key = None
            self.errorOccurred.emit(error)
            self.refresh()
            return
        if self._active_key != key:
            self._active_key = key
            self._model.set_active(key)
            self._emit_active_key_if_changed(key)

    def _handle_create_result(self, ok: bool, error: str, key: str) -> None:
        if self._disposed:
            return
        self._pending_creates.discard(key)
        self.refresh()
        if not ok:
            self.errorOccurred.emit(error)

    def _handle_delete_result(self, key: str, ok: bool, error: str) -> None:
        if self._disposed:
            return
        snapshot = self._pending_deletes.pop(key, None)
        if not ok:
            if snapshot is not None:
                sessions_before, active_before, optimistic_active = snapshot
                if self._active_key == optimistic_active:
                    pending_keys = set(self._pending_deletes.keys())
                    if pending_keys:
                        sessions_before = [
                            s for s in sessions_before if str(s.get("key", "")) not in pending_keys
                        ]
                        if active_before in pending_keys:
                            active_before = self._active_key
                    self._active_key = active_before
                    for item in sessions_before:
                        if str(item.get("key", "")) == active_before:
                            item["has_unread"] = False
                    self._model.reset_sessions(sessions_before, active_before)
                    self.sessionsChanged.emit()
                    self._emit_active_key_if_changed(active_before)
                else:
                    self.refresh()
            self.errorOccurred.emit(error)
            self.deleteCompleted.emit(key, False, error)
            return
        # Optimistic update already reflects correct state — skip refresh
        # to avoid a redundant full rebuild that causes list flicker.
        self.deleteCompleted.emit(key, True, "")
