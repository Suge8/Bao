"""SessionService — wraps Bao SessionManager for the desktop channel.

All SessionManager calls are dispatched to the asyncio thread via AsyncioRunner.
Internal signals marshal results back to the Qt main thread.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import os
from loguru import logger

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QModelIndex,
    QObject,
    Qt,
    QTimer,
    Signal,
    Slot,
)

from app.backend.asyncio_runner import AsyncioRunner

_DEBUG_SWITCH = os.getenv("BAO_DESKTOP_DEBUG_SWITCH") == "1"


class SessionListModel(QAbstractListModel):
    """Simple list model exposing session dicts to QML."""

    _ROLES = {
        Qt.UserRole + 1: b"key",
        Qt.UserRole + 2: b"title",
        Qt.UserRole + 3: b"isActive",
        Qt.UserRole + 4: b"updatedAt",
        Qt.UserRole + 5: b"channel",
        Qt.UserRole + 6: b"hasUnread",
    }

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._sessions: list[dict[str, Any]] = []
        self._active_key: str = ""
        self._unread_keys: set[str] = set()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return len(self._sessions)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._sessions)):
            return None
        s = self._sessions[index.row()]
        if role == Qt.UserRole + 1:
            return s.get("key", "")
        if role == Qt.UserRole + 2:
            return s.get("title", s.get("key", ""))
        if role == Qt.UserRole + 3:
            return s.get("key", "") == self._active_key
        if role == Qt.UserRole + 4:
            return s.get("updated_at", 0)
        if role == Qt.UserRole + 5:
            return s.get("channel", "other")
        if role == Qt.UserRole + 6:
            return s.get("key", "") in self._unread_keys
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {int(k): v for k, v in self._ROLES.items()}

    def reset_sessions(
        self, sessions: list[dict[str, Any]], active_key: str,
        unread_keys: set[str] | None = None,
    ) -> None:
        self.beginResetModel()
        self._sessions = sessions
        self._active_key = active_key
        if unread_keys is not None:
            self._unread_keys = unread_keys
        self.endResetModel()

    def set_active(self, key: str) -> None:
        if self._active_key == key:
            return
        old_key = self._active_key
        self._active_key = key
        for i, s in enumerate(self._sessions):
            if s.get("key") in (old_key, key):
                idx = self.index(i)
                self.dataChanged.emit(idx, idx, [Qt.UserRole + 3])


class SessionService(QObject):
    sessionsChanged = Signal()
    activeKeyChanged = Signal(str)
    errorOccurred = Signal(str)
    deleteCompleted = Signal(str, bool, str)

    # Internal signals: asyncio thread → Qt main thread
    _listResult = Signal(bool, str, object)  # ok, error, (sessions, active)
    _selectResult = Signal(bool, str, str)  # ok, error, key
    _mutateResult = Signal(bool, str)  # ok, error (for create/delete)
    _deleteResult = Signal(str, bool, str)

    def __init__(self, runner: AsyncioRunner, parent: Any = None) -> None:
        super().__init__(parent)
        self._runner = runner
        self._session_manager: Any = None
        self._natural_key = "desktop:local"
        self._allow_active_selection = False
        self._active_key = ""
        self._pending_select_key: str | None = None
        self._last_emitted_active_key = ""
        self._model = SessionListModel()
        self._pending_deletes: dict[str, tuple[list[dict[str, Any]], str]] = {}
        self._list_fp: tuple[Any, ...] | None = None
        self._unread_timer = QTimer(self)
        self._unread_timer.setInterval(5000)
        self._unread_timer.timeout.connect(self.refresh)

        self._listResult.connect(self._handle_list_result)
        self._selectResult.connect(self._handle_select_result)
        self._mutateResult.connect(self._handle_mutate_result)
        self._deleteResult.connect(self._handle_delete_result)

    @Property(QObject, constant=True)
    def sessionsModel(self) -> SessionListModel:
        return self._model

    @Property(str, notify=activeKeyChanged)
    def activeKey(self) -> str:
        return self._active_key

    def initialize(self, session_manager: Any) -> None:
        """Called after ChatService has initialized the Bao SessionManager."""
        self._session_manager = session_manager
        self.refresh()
        self._unread_timer.start()

    def _emit_active_key_if_changed(self, new_key: str) -> None:
        """Emit activeKeyChanged only if key actually changed."""
        if new_key != self._last_emitted_active_key:
            self._last_emitted_active_key = new_key
            self.activeKeyChanged.emit(new_key)
    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        if self._session_manager is None:
            return
        fut = self._runner.submit(self._list_sessions())
        fut.add_done_callback(self._on_list_done)

    @Slot()
    def setGatewayReady(self) -> None:
        self._allow_active_selection = True

    @Slot(str)
    def newSession(self, name: str = "") -> None:
        fut = self._runner.submit(self._create_session(name))
        fut.add_done_callback(self._on_mutate_done)

    @Slot(str)
    def selectSession(self, key: str) -> None:
        if _DEBUG_SWITCH:
            logger.debug(f"session_select_request key={key}")
        if not key:
            return
        # Mark old + new session as read (fire-and-forget)
        old_key = self._active_key
        if old_key and old_key != key:
            self._runner.submit(self._mark_read(old_key))
            self._model._unread_keys.discard(old_key)
        self._runner.submit(self._mark_read(key))
        self._model._unread_keys.discard(key)
        self._pending_select_key = key
        if self._active_key != key:
            self._allow_active_selection = True
            self._active_key = key
            self._model.set_active(key)
            if _DEBUG_SWITCH:
                logger.debug(f"session_select_commit key={key}")
            self._emit_active_key_if_changed(key)
        fut = self._runner.submit(self._select_session(key))
        fut.add_done_callback(self._on_select_done)

    @Slot(str)
    def deleteSession(self, key: str) -> None:
        if not key or self._session_manager is None or key in self._pending_deletes:
            return
        sessions_before = [dict(s) for s in self._model._sessions]
        active_before = self._active_key
        sessions_after = [s for s in sessions_before if s.get("key") != key]
        if len(sessions_after) == len(sessions_before):
            return

        new_active = active_before
        if active_before == key:
            if sessions_after:
                desktop = [s for s in sessions_after if s.get("channel") == "desktop"]
                pick = desktop[0] if desktop else sessions_after[0]
                new_active = str(pick.get("key", ""))
            else:
                new_active = ""

        self._pending_deletes[key] = (sessions_before, active_before)
        self._active_key = new_active
        self._model.reset_sessions(sessions_after, new_active)
        self.sessionsChanged.emit()
        self._emit_active_key_if_changed(new_active)

        fut = self._runner.submit(self._delete_session(key))
        fut.add_done_callback(lambda future, k=key: self._on_delete_done(k, future))

    # ------------------------------------------------------------------
    # Async helpers (run on asyncio thread)
    # ------------------------------------------------------------------

    async def _list_sessions(self) -> tuple[list[dict], str, set[str]]:
        sm = self._session_manager
        sessions = sm.list_sessions()
        active = sm.get_active_session_key(self._natural_key) or ""
        result = []
        unread_keys: set[str] = set()
        for s in sessions:
            key = s["key"]
            channel = key.split(":")[0] if ":" in key else (key if key == "heartbeat" else "other")
            meta = s.get("metadata", {})
            last_read = meta.get("desktop_last_read_at")
            updated = s.get("updated_at", "")
            if last_read and updated > last_read:
                unread_keys.add(key)
            result.append(
                {
                    "key": key,
                    "title": meta.get("title") or key,
                    "updated_at": updated,
                    "channel": channel,
                }
            )
        return result, active, unread_keys

    async def _create_session(self, name: str) -> str:
        sm = self._session_manager
        if name:
            key = f"{self._natural_key}::{name}"
        else:
            import time

            key = f"{self._natural_key}::session-{int(time.time())}"
        # Create session in storage so it appears in list_sessions immediately
        session = sm.get_or_create(key)
        sm.save(session)
        sm.set_active_session_key(self._natural_key, key)
        return key

    async def _select_session(self, key: str) -> str:
        self._session_manager.set_active_session_key(self._natural_key, key)
        return key

    async def _mark_read(self, key: str) -> None:
        sm = self._session_manager
        session = sm.get_or_create(key)
        session.metadata["desktop_last_read_at"] = datetime.now().isoformat()
        sm.save(session)

    async def _delete_session(self, key: str) -> None:
        was_active = self._session_manager.get_active_session_key(self._natural_key) == key
        self._session_manager.delete_session(key)
        if was_active:
            self._session_manager.clear_active_session_key(self._natural_key)

    # ------------------------------------------------------------------
    # Callbacks (asyncio thread — emit signals only, no Qt ops)
    # ------------------------------------------------------------------

    def _on_list_done(self, future: Any) -> None:
        exc = future.exception()
        if exc:
            self._listResult.emit(False, str(exc), None)
        else:
            self._listResult.emit(True, "", future.result())

    def _on_select_done(self, future: Any) -> None:
        exc = future.exception()
        if exc:
            self._selectResult.emit(False, str(exc), "")
        else:
            self._selectResult.emit(True, "", future.result())

    def _on_mutate_done(self, future: Any) -> None:
        exc = future.exception()
        if exc:
            self._mutateResult.emit(False, str(exc))
        else:
            self._mutateResult.emit(True, "")

    def _on_delete_done(self, key: str, future: Any) -> None:
        exc = future.exception()
        if exc:
            self._deleteResult.emit(key, False, str(exc))
        else:
            self._deleteResult.emit(key, True, "")

    # ------------------------------------------------------------------
    # Main-thread handlers (connected via signals)
    # ------------------------------------------------------------------

    def _handle_list_result(self, ok: bool, error: str, data: Any) -> None:
        if not ok:
            self.errorOccurred.emit(error)
            return
        sessions, active, unread_keys = data
        if not self._allow_active_selection:
            active = ""
        elif not active and sessions:
            desktop = [s for s in sessions if s.get("channel") == "desktop"]
            pick = desktop[0] if desktop else sessions[0]
            active = pick["key"]
            if self._session_manager:
                self._session_manager.set_active_session_key(self._natural_key, active)
        # Active session is always "read" — prevent stale poll from re-adding red dot
        if self._active_key:
            unread_keys.discard(self._active_key)
        # Fingerprint check — skip rebuild if nothing changed
        fp = (
            tuple((s["key"], s.get("title", "")) for s in sessions),
            active, frozenset(unread_keys),
        )
        if self._list_fp == fp:
            return
        self._list_fp = fp
        self._active_key = active
        self._model.reset_sessions(sessions, active, unread_keys)
        self.sessionsChanged.emit()
        if active:
            self._emit_active_key_if_changed(active)

    def _handle_select_result(self, ok: bool, error: str, key: str) -> None:
        if self._pending_select_key is not None and key != self._pending_select_key:
            return
        self._pending_select_key = None
        if not ok:
            self.errorOccurred.emit(error)
            self.refresh()
            return
        self._allow_active_selection = True
        if self._active_key != key:
            self._active_key = key
            self._model.set_active(key)
            self._emit_active_key_if_changed(key)

    def _handle_mutate_result(self, ok: bool, error: str) -> None:
        if not ok:
            self.errorOccurred.emit(error)
            return
        self.refresh()

    def _handle_delete_result(self, key: str, ok: bool, error: str) -> None:
        snapshot = self._pending_deletes.pop(key, None)
        if not ok:
            if snapshot is not None:
                sessions_before, active_before = snapshot
                self._active_key = active_before
                self._model.reset_sessions(sessions_before, active_before)
                self.sessionsChanged.emit()
                self._emit_active_key_if_changed(active_before)
            self.errorOccurred.emit(error)
            self.deleteCompleted.emit(key, False, error)
            return
        # Optimistic update already reflects correct state — skip refresh
        # to avoid a redundant full rebuild that causes list flicker.
        self.deleteCompleted.emit(key, True, "")
