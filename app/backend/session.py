"""SessionService — wraps bao SessionManager for the desktop channel.

All SessionManager calls are dispatched to the asyncio thread via AsyncioRunner.
Internal signals marshal results back to the Qt main thread.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, QObject, Qt, Signal, Slot, Property

from app.backend.asyncio_runner import AsyncioRunner


class SessionListModel(QAbstractListModel):
    """Simple list model exposing session dicts to QML."""

    _ROLES = {
        Qt.UserRole + 1: b"key",
        Qt.UserRole + 2: b"title",
        Qt.UserRole + 3: b"isActive",
        Qt.UserRole + 4: b"updatedAt",
    }

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._sessions: list[dict[str, Any]] = []
        self._active_key: str = ""

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
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {int(k): v for k, v in self._ROLES.items()}

    def reset_sessions(self, sessions: list[dict[str, Any]], active_key: str) -> None:
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
                self.dataChanged.emit(idx, idx, [Qt.UserRole + 3])


class SessionService(QObject):
    sessionsChanged = Signal()
    activeKeyChanged = Signal(str)
    errorOccurred = Signal(str)

    # Internal signals: asyncio thread → Qt main thread
    _listResult = Signal(bool, str, object)  # ok, error, (sessions, active)
    _selectResult = Signal(bool, str, str)  # ok, error, key
    _mutateResult = Signal(bool, str)  # ok, error (for create/delete)

    def __init__(self, runner: AsyncioRunner, parent: Any = None) -> None:
        super().__init__(parent)
        self._runner = runner
        self._session_manager: Any = None
        self._natural_key = "desktop:local"
        self._active_key = ""
        self._model = SessionListModel()

        self._listResult.connect(self._handle_list_result)
        self._selectResult.connect(self._handle_select_result)
        self._mutateResult.connect(self._handle_mutate_result)

    @Property(QObject, constant=True)
    def sessionsModel(self) -> SessionListModel:
        return self._model

    @Property(str, notify=activeKeyChanged)
    def activeKey(self) -> str:
        return self._active_key

    def initialize(self, session_manager: Any) -> None:
        """Called after ChatService has initialized the bao SessionManager."""
        self._session_manager = session_manager
        self.refresh()

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        if self._session_manager is None:
            return
        fut = self._runner.submit(self._list_sessions())
        fut.add_done_callback(self._on_list_done)

    @Slot(str)
    def newSession(self, name: str = "") -> None:
        fut = self._runner.submit(self._create_session(name))
        fut.add_done_callback(self._on_mutate_done)

    @Slot(str)
    def selectSession(self, key: str) -> None:
        fut = self._runner.submit(self._select_session(key))
        fut.add_done_callback(self._on_select_done)

    @Slot(str)
    def deleteSession(self, key: str) -> None:
        fut = self._runner.submit(self._delete_session(key))
        fut.add_done_callback(self._on_mutate_done)

    # ------------------------------------------------------------------
    # Async helpers (run on asyncio thread)
    # ------------------------------------------------------------------

    async def _list_sessions(self) -> tuple[list[dict], str]:
        sm = self._session_manager
        sessions = sm.list_sessions()
        active = sm.get_active_session_key(self._natural_key) or ""
        result = []
        for s in sessions:
            result.append(
                {
                    "key": s["key"],
                    "title": s.get("metadata", {}).get("title") or s["key"],
                    "updated_at": s.get("updated_at", 0),
                }
            )
        return result, active

    async def _create_session(self, name: str) -> str:
        sm = self._session_manager
        if name:
            key = f"{self._natural_key}::{name}"
        else:
            import time

            key = f"{self._natural_key}::session-{int(time.time())}"
        sm.set_active_session_key(self._natural_key, key)
        return key

    async def _select_session(self, key: str) -> str:
        self._session_manager.set_active_session_key(self._natural_key, key)
        return key

    async def _delete_session(self, key: str) -> None:
        self._session_manager.delete_session(key)
        if self._active_key == key:
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

    # ------------------------------------------------------------------
    # Main-thread handlers (connected via signals)
    # ------------------------------------------------------------------

    def _handle_list_result(self, ok: bool, error: str, data: Any) -> None:
        if not ok:
            self.errorOccurred.emit(error)
            return
        sessions, active = data
        self._active_key = active
        self._model.reset_sessions(sessions, active)
        self.sessionsChanged.emit()

    def _handle_select_result(self, ok: bool, error: str, key: str) -> None:
        if not ok:
            self.errorOccurred.emit(error)
            return
        self._active_key = key
        self._model.set_active(key)
        self.activeKeyChanged.emit(key)

    def _handle_mutate_result(self, ok: bool, error: str) -> None:
        if not ok:
            self.errorOccurred.emit(error)
            return
        self.refresh()
