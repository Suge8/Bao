"""SessionService — wraps Bao SessionManager for the desktop channel.

All SessionManager calls are dispatched to the asyncio thread via AsyncioRunner.
Internal signals marshal results back to the Qt main thread.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from concurrent.futures import CancelledError as FutureCancelledError
from pathlib import Path
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

from app.backend import session_projection
from app.backend.asyncio_runner import AsyncioRunner
from app.backend.session_projection import (
    ActiveSessionProjection,
    build_session_item,
    build_sidebar_projection,
    filter_session_dicts,
    normalize_session_item,
    normalize_session_items,
    pick_latest_key,
    project_active_session,
    project_session_item,
    running_parent_keys,
    session_channel_key,
    session_sort_value,
    tail_backfill_keys,
    title_by_key,
    visible_session_key,
    visible_session_key_for_channel,
    visible_sidebar_items,
)
from bao.session.manager import SessionChangeEvent

_format_display_title = session_projection.format_display_title
_format_updated_label = session_projection.format_updated_label
_visible_sidebar_items = visible_sidebar_items

_DEBUG_SWITCH = os.getenv("BAO_DESKTOP_DEBUG_SWITCH") == "1"
_ROLE_BASE = int(Qt.ItemDataRole.UserRole)
_ROLE_KEY = _ROLE_BASE + 1
_ROLE_TITLE = _ROLE_BASE + 2
_ROLE_IS_ACTIVE = _ROLE_BASE + 3
_ROLE_UPDATED_AT = _ROLE_BASE + 4
_ROLE_CHANNEL = _ROLE_BASE + 5
_ROLE_HAS_UNREAD = _ROLE_BASE + 6
_ROLE_UPDATED_LABEL = _ROLE_BASE + 7
_ROLE_MESSAGE_COUNT = _ROLE_BASE + 8
_ROLE_HAS_MESSAGES = _ROLE_BASE + 9
_ROLE_SESSION_KIND = _ROLE_BASE + 10
_ROLE_IS_READ_ONLY = _ROLE_BASE + 11
_ROLE_PARENT_SESSION_KEY = _ROLE_BASE + 12
_ROLE_PARENT_TITLE = _ROLE_BASE + 13
_ROLE_CHILD_STATUS = _ROLE_BASE + 14
_ROLE_IS_RUNNING = _ROLE_BASE + 15

_SIDEBAR_ROLE_BASE = _ROLE_BASE + 100
_SIDEBAR_ROLE_ROW_ID = _SIDEBAR_ROLE_BASE + 1
_SIDEBAR_ROLE_IS_HEADER = _SIDEBAR_ROLE_BASE + 2
_SIDEBAR_ROLE_CHANNEL = _SIDEBAR_ROLE_BASE + 3
_SIDEBAR_ROLE_EXPANDED = _SIDEBAR_ROLE_BASE + 4
_SIDEBAR_ROLE_ITEM_KEY = _SIDEBAR_ROLE_BASE + 5
_SIDEBAR_ROLE_ITEM_TITLE = _SIDEBAR_ROLE_BASE + 6
_SIDEBAR_ROLE_ITEM_UPDATED_TEXT = _SIDEBAR_ROLE_BASE + 7
_SIDEBAR_ROLE_VISUAL_CHANNEL = _SIDEBAR_ROLE_BASE + 8
_SIDEBAR_ROLE_IS_READ_ONLY = _SIDEBAR_ROLE_BASE + 9
_SIDEBAR_ROLE_IS_RUNNING = _SIDEBAR_ROLE_BASE + 10
_SIDEBAR_ROLE_IS_CHILD_SESSION = _SIDEBAR_ROLE_BASE + 11
_SIDEBAR_ROLE_PARENT_SESSION_KEY = _SIDEBAR_ROLE_BASE + 12
_SIDEBAR_ROLE_RESERVED_ITEM_VISIBLE = _SIDEBAR_ROLE_BASE + 13
_SIDEBAR_ROLE_ITEM_HAS_UNREAD = _SIDEBAR_ROLE_BASE + 14
_SIDEBAR_ROLE_ITEM_COUNT = _SIDEBAR_ROLE_BASE + 15
_SIDEBAR_ROLE_GROUP_UNREAD_COUNT = _SIDEBAR_ROLE_BASE + 16
_SIDEBAR_ROLE_GROUP_HAS_RUNNING = _SIDEBAR_ROLE_BASE + 17
_SIDEBAR_ROLE_IS_LAST_IN_GROUP = _SIDEBAR_ROLE_BASE + 18
_SIDEBAR_ROLE_IS_FIRST_IN_GROUP = _SIDEBAR_ROLE_BASE + 19

_SIDEBAR_FIELD_TO_ROLE = {
    "row_id": _SIDEBAR_ROLE_ROW_ID,
    "is_header": _SIDEBAR_ROLE_IS_HEADER,
    "channel": _SIDEBAR_ROLE_CHANNEL,
    "expanded": _SIDEBAR_ROLE_EXPANDED,
    "item_key": _SIDEBAR_ROLE_ITEM_KEY,
    "item_title": _SIDEBAR_ROLE_ITEM_TITLE,
    "item_updated_text": _SIDEBAR_ROLE_ITEM_UPDATED_TEXT,
    "visual_channel": _SIDEBAR_ROLE_VISUAL_CHANNEL,
    "is_read_only": _SIDEBAR_ROLE_IS_READ_ONLY,
    "is_running": _SIDEBAR_ROLE_IS_RUNNING,
    "is_child_session": _SIDEBAR_ROLE_IS_CHILD_SESSION,
    "parent_session_key": _SIDEBAR_ROLE_PARENT_SESSION_KEY,
    "item_has_unread": _SIDEBAR_ROLE_ITEM_HAS_UNREAD,
    "item_count": _SIDEBAR_ROLE_ITEM_COUNT,
    "group_unread_count": _SIDEBAR_ROLE_GROUP_UNREAD_COUNT,
    "group_has_running": _SIDEBAR_ROLE_GROUP_HAS_RUNNING,
    "is_last_in_group": _SIDEBAR_ROLE_IS_LAST_IN_GROUP,
    "is_first_in_group": _SIDEBAR_ROLE_IS_FIRST_IN_GROUP,
}

_SESSION_FIELD_TO_ROLE = {
    "key": _ROLE_KEY,
    "title": _ROLE_TITLE,
    "updated_at": _ROLE_UPDATED_AT,
    "channel": _ROLE_CHANNEL,
    "has_unread": _ROLE_HAS_UNREAD,
    "updated_label": _ROLE_UPDATED_LABEL,
    "message_count": _ROLE_MESSAGE_COUNT,
    "has_messages": _ROLE_HAS_MESSAGES,
    "session_kind": _ROLE_SESSION_KIND,
    "is_read_only": _ROLE_IS_READ_ONLY,
    "parent_session_key": _ROLE_PARENT_SESSION_KEY,
    "parent_title": _ROLE_PARENT_TITLE,
    "child_status": _ROLE_CHILD_STATUS,
    "is_running": _ROLE_IS_RUNNING,
}


class SidebarRowsModel(QAbstractListModel):
    _ROLES = {
        _SIDEBAR_ROLE_ROW_ID: QByteArray(b"rowId"),
        _SIDEBAR_ROLE_IS_HEADER: QByteArray(b"isHeader"),
        _SIDEBAR_ROLE_CHANNEL: QByteArray(b"channel"),
        _SIDEBAR_ROLE_EXPANDED: QByteArray(b"expanded"),
        _SIDEBAR_ROLE_ITEM_KEY: QByteArray(b"itemKey"),
        _SIDEBAR_ROLE_ITEM_TITLE: QByteArray(b"itemTitle"),
        _SIDEBAR_ROLE_ITEM_UPDATED_TEXT: QByteArray(b"itemUpdatedText"),
        _SIDEBAR_ROLE_VISUAL_CHANNEL: QByteArray(b"visualChannel"),
        _SIDEBAR_ROLE_IS_READ_ONLY: QByteArray(b"isReadOnly"),
        _SIDEBAR_ROLE_IS_RUNNING: QByteArray(b"isRunning"),
        _SIDEBAR_ROLE_IS_CHILD_SESSION: QByteArray(b"isChildSession"),
        _SIDEBAR_ROLE_PARENT_SESSION_KEY: QByteArray(b"parentSessionKey"),
        _SIDEBAR_ROLE_ITEM_HAS_UNREAD: QByteArray(b"itemHasUnread"),
        _SIDEBAR_ROLE_ITEM_COUNT: QByteArray(b"itemCount"),
        _SIDEBAR_ROLE_GROUP_UNREAD_COUNT: QByteArray(b"groupUnreadCount"),
        _SIDEBAR_ROLE_GROUP_HAS_RUNNING: QByteArray(b"groupHasRunning"),
        _SIDEBAR_ROLE_IS_LAST_IN_GROUP: QByteArray(b"isLastInGroup"),
        _SIDEBAR_ROLE_IS_FIRST_IN_GROUP: QByteArray(b"isFirstInGroup"),
    }

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._rows)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        if role == _SIDEBAR_ROLE_ROW_ID:
            return row.get("row_id", "")
        if role == _SIDEBAR_ROLE_IS_HEADER:
            return bool(row.get("is_header", False))
        if role == _SIDEBAR_ROLE_CHANNEL:
            return row.get("channel", "other")
        if role == _SIDEBAR_ROLE_EXPANDED:
            return bool(row.get("expanded", False))
        if role == _SIDEBAR_ROLE_ITEM_KEY:
            return row.get("item_key", "")
        if role == _SIDEBAR_ROLE_ITEM_TITLE:
            return row.get("item_title", "")
        if role == _SIDEBAR_ROLE_ITEM_UPDATED_TEXT:
            return row.get("item_updated_text", "")
        if role == _SIDEBAR_ROLE_VISUAL_CHANNEL:
            return row.get("visual_channel", row.get("channel", "other"))
        if role == _SIDEBAR_ROLE_IS_READ_ONLY:
            return bool(row.get("is_read_only", False))
        if role == _SIDEBAR_ROLE_IS_RUNNING:
            return bool(row.get("is_running", False))
        if role == _SIDEBAR_ROLE_IS_CHILD_SESSION:
            return bool(row.get("is_child_session", False))
        if role == _SIDEBAR_ROLE_PARENT_SESSION_KEY:
            return row.get("parent_session_key", "")
        if role == _SIDEBAR_ROLE_ITEM_HAS_UNREAD:
            return bool(row.get("item_has_unread", False))
        if role == _SIDEBAR_ROLE_ITEM_COUNT:
            return int(row.get("item_count", 0) or 0)
        if role == _SIDEBAR_ROLE_GROUP_UNREAD_COUNT:
            return int(row.get("group_unread_count", 0) or 0)
        if role == _SIDEBAR_ROLE_GROUP_HAS_RUNNING:
            return bool(row.get("group_has_running", False))
        if role == _SIDEBAR_ROLE_IS_LAST_IN_GROUP:
            return bool(row.get("is_last_in_group", False))
        if role == _SIDEBAR_ROLE_IS_FIRST_IN_GROUP:
            return bool(row.get("is_first_in_group", False))
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return dict(self._ROLES)

    def active_row_index(self, key: str) -> int:
        row_id = f"session:{key}"
        for index, row in enumerate(self._rows):
            if str(row.get("row_id", "")) == row_id:
                return index
        return -1

    def sync_rows(self, rows: list[dict[str, Any]]) -> None:
        next_rows = [dict(row) for row in rows]
        next_ids = {str(row.get("row_id", "")) for row in next_rows}
        for remove_index in range(len(self._rows) - 1, -1, -1):
            if str(self._rows[remove_index].get("row_id", "")) in next_ids:
                continue
            self.beginRemoveRows(QModelIndex(), remove_index, remove_index)
            del self._rows[remove_index]
            self.endRemoveRows()

        row_index = 0
        while row_index < len(next_rows):
            next_row = next_rows[row_index]
            next_id = str(next_row.get("row_id", ""))
            if (
                row_index < len(self._rows)
                and str(self._rows[row_index].get("row_id", "")) == next_id
            ):
                self._update_row(row_index, next_row)
                row_index += 1
                continue

            found_index = -1
            for search_index in range(row_index + 1, len(self._rows)):
                if str(self._rows[search_index].get("row_id", "")) == next_id:
                    found_index = search_index
                    break
            if found_index >= 0:
                self.beginMoveRows(
                    QModelIndex(), found_index, found_index, QModelIndex(), row_index
                )
                row = self._rows.pop(found_index)
                self._rows.insert(row_index, row)
                self.endMoveRows()
            else:
                self.beginInsertRows(QModelIndex(), row_index, row_index)
                self._rows.insert(row_index, dict(next_row))
                self.endInsertRows()
            self._update_row(row_index, next_row)
            row_index += 1

    def clear_rows(self) -> None:
        if not self._rows:
            return
        self.beginResetModel()
        self._rows = []
        self.endResetModel()

    def _update_row(self, index: int, next_row: dict[str, Any]) -> None:
        current = self._rows[index]
        changed_roles: list[int] = []
        for field, role in _SIDEBAR_FIELD_TO_ROLE.items():
            next_value = next_row.get(field)
            if current.get(field) == next_value:
                continue
            current[field] = next_value
            changed_roles.append(role)
        if not changed_roles:
            return
        model_index = self.index(index)
        self.dataChanged.emit(model_index, model_index, changed_roles)


class SessionListModel(QAbstractListModel):
    """Simple list model exposing session dicts to QML."""

    _ROLES = {
        _ROLE_KEY: QByteArray(b"key"),
        _ROLE_TITLE: QByteArray(b"title"),
        _ROLE_IS_ACTIVE: QByteArray(b"isActive"),
        _ROLE_UPDATED_AT: QByteArray(b"updatedAt"),
        _ROLE_CHANNEL: QByteArray(b"channel"),
        _ROLE_HAS_UNREAD: QByteArray(b"hasUnread"),
        _ROLE_UPDATED_LABEL: QByteArray(b"updatedLabel"),
        _ROLE_MESSAGE_COUNT: QByteArray(b"messageCount"),
        _ROLE_HAS_MESSAGES: QByteArray(b"hasMessages"),
        _ROLE_SESSION_KIND: QByteArray(b"sessionKind"),
        _ROLE_IS_READ_ONLY: QByteArray(b"isReadOnly"),
        _ROLE_PARENT_SESSION_KEY: QByteArray(b"parentSessionKey"),
        _ROLE_PARENT_TITLE: QByteArray(b"parentTitle"),
        _ROLE_CHILD_STATUS: QByteArray(b"childStatus"),
        _ROLE_IS_RUNNING: QByteArray(b"isRunning"),
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
            title = s.get("title", "")
            if isinstance(title, str) and title:
                return title
            return s.get("key", "")
        if role == _ROLE_IS_ACTIVE:
            return s.get("key", "") == self._active_key
        if role == _ROLE_UPDATED_AT:
            return s.get("updated_at", 0)
        if role == _ROLE_CHANNEL:
            return s.get("channel", "other")
        if role == _ROLE_HAS_UNREAD:
            return bool(s.get("has_unread", False))
        if role == _ROLE_UPDATED_LABEL:
            return s.get("updated_label", "")
        if role == _ROLE_MESSAGE_COUNT:
            return s.get("message_count")
        if role == _ROLE_HAS_MESSAGES:
            return s.get("has_messages")
        if role == _ROLE_SESSION_KIND:
            return s.get("session_kind", "regular")
        if role == _ROLE_IS_READ_ONLY:
            return bool(s.get("is_read_only", False))
        if role == _ROLE_PARENT_SESSION_KEY:
            return s.get("parent_session_key", "")
        if role == _ROLE_PARENT_TITLE:
            return s.get("parent_title", "")
        if role == _ROLE_CHILD_STATUS:
            return s.get("child_status", "")
        if role == _ROLE_IS_RUNNING:
            return bool(s.get("is_running", False))
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return dict(self._ROLES)

    def reset_sessions(
        self,
        sessions: list[dict[str, Any]],
        active_key: str,
    ) -> None:
        self.beginResetModel()
        self._sessions = [dict(session) for session in sessions]
        self._active_key = active_key
        self.endResetModel()

    def sync_sessions(
        self,
        sessions: list[dict[str, Any]],
        active_key: str,
    ) -> None:
        next_sessions = [dict(session) for session in sessions]
        next_keys = {str(session.get("key", "")) for session in next_sessions}
        for remove_index in range(len(self._sessions) - 1, -1, -1):
            if str(self._sessions[remove_index].get("key", "")) in next_keys:
                continue
            self.beginRemoveRows(QModelIndex(), remove_index, remove_index)
            del self._sessions[remove_index]
            self.endRemoveRows()

        row_index = 0
        while row_index < len(next_sessions):
            next_session = next_sessions[row_index]
            next_key = str(next_session.get("key", ""))
            if (
                row_index < len(self._sessions)
                and str(self._sessions[row_index].get("key", "")) == next_key
            ):
                self._update_session_row(row_index, next_session)
                row_index += 1
                continue

            found_index = -1
            for search_index in range(row_index + 1, len(self._sessions)):
                if str(self._sessions[search_index].get("key", "")) == next_key:
                    found_index = search_index
                    break
            if found_index >= 0:
                self.beginMoveRows(
                    QModelIndex(), found_index, found_index, QModelIndex(), row_index
                )
                session = self._sessions.pop(found_index)
                self._sessions.insert(row_index, session)
                self.endMoveRows()
            else:
                self.beginInsertRows(QModelIndex(), row_index, row_index)
                self._sessions.insert(row_index, dict(next_session))
                self.endInsertRows()
            self._update_session_row(row_index, next_session)
            row_index += 1

        self._apply_active_key(active_key)

    def _update_session_row(self, index: int, next_session: dict[str, Any]) -> None:
        current = self._sessions[index]
        changed_roles: list[int] = []
        for field, role in _SESSION_FIELD_TO_ROLE.items():
            next_value = next_session.get(field)
            if current.get(field) == next_value:
                continue
            current[field] = next_value
            changed_roles.append(role)
        for field in ("self_running", "needs_tail_backfill"):
            current[field] = next_session.get(field)
        if not changed_roles:
            return
        model_index = self.index(index)
        self.dataChanged.emit(model_index, model_index, changed_roles)

    def _find_session_index(self, key: str) -> int:
        for index, session in enumerate(self._sessions):
            if str(session.get("key", "")) == key:
                return index
        return -1

    def _target_index_for_session(self, next_session: dict[str, Any], *, skip_index: int = -1) -> int:
        next_sort = session_sort_value(next_session)
        target_index = 0
        for index, session in enumerate(self._sessions):
            if index == skip_index:
                continue
            if session_sort_value(session) >= next_sort:
                target_index += 1
                continue
            break
        return target_index

    def upsert_sessions(
        self,
        sessions: list[dict[str, Any]],
        active_key: str,
    ) -> None:
        for next_session in sessions:
            next_key = str(next_session.get("key", ""))
            if not next_key:
                continue
            existing_index = self._find_session_index(next_key)
            if existing_index < 0:
                target_index = self._target_index_for_session(next_session)
                self.beginInsertRows(QModelIndex(), target_index, target_index)
                self._sessions.insert(target_index, dict(next_session))
                self.endInsertRows()
                self._update_session_row(target_index, next_session)
                continue

            self._update_session_row(existing_index, next_session)
            target_index = self._target_index_for_session(next_session, skip_index=existing_index)
            if target_index == existing_index:
                continue
            destination = target_index if target_index < existing_index else target_index + 1
            self.beginMoveRows(
                QModelIndex(),
                existing_index,
                existing_index,
                QModelIndex(),
                destination,
            )
            session = self._sessions.pop(existing_index)
            insert_index = target_index if target_index < existing_index else target_index
            self._sessions.insert(insert_index, session)
            self.endMoveRows()

        self._apply_active_key(active_key)

    def _apply_active_key(self, key: str) -> None:
        old_key = self._active_key
        self._active_key = key
        affected_keys = {old_key, key}
        for index, session in enumerate(self._sessions):
            session_key = str(session.get("key", ""))
            changed_roles: list[int] = []
            if session_key == key and session.get("has_unread"):
                session["has_unread"] = False
                changed_roles.append(_ROLE_HAS_UNREAD)
            if session_key in affected_keys:
                changed_roles.append(_ROLE_IS_ACTIVE)
            if not changed_roles:
                continue
            model_index = self.index(index)
            self.dataChanged.emit(model_index, model_index, changed_roles)

    def set_active(self, key: str) -> None:
        self._apply_active_key(key)


class SessionService(QObject):
    sessionsChanged = Signal()
    sidebarProjectionWillChange = Signal()
    sidebarProjectionChanged = Signal()
    activeKeyChanged = Signal(str)
    activeSummaryChanged = Signal(str, object, object)
    activeReady = Signal(str)
    startupTargetReady = Signal(str)
    activeSessionMetaChanged = Signal()
    sessionsLoadingChanged = Signal(bool)
    errorOccurred = Signal(str)
    deleteCompleted = Signal(str, bool, str)
    sessionManagerReady = Signal(object)

    # Internal signals: asyncio thread → Qt main thread
    _bootstrapResult = Signal(bool, str, object)
    _listResult = Signal(bool, str, object)  # ok, error, (sessions, active)
    _selectResult = Signal(bool, str, str)  # ok, error, key
    _createResult = Signal(bool, str, str)  # ok, error, key
    _deleteResult = Signal(str, bool, str)
    _sessionChange = Signal(object)
    _sessionEntryResult = Signal(bool, str, object)  # ok, error, (key, seq, generation, session_entry)

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
        self._sidebar_model = SidebarRowsModel()
        self._sidebar_expanded_groups: dict[str, bool] = {}
        self._sidebar_unread_count = 0
        self._sidebar_unread_fingerprint = ""
        self._pending_deletes: dict[
            str,
            tuple[list[dict[str, Any]], str, str, dict[str, bool]],
        ] = {}
        self._pending_creates: set[str] = set()
        self._list_request_seq = 0
        self._list_latest_seq = 0
        self._list_inflight_count = 0
        self._sessions_loading = False
        self._active_commit_seq = 0
        self._bootstrap_storage_root = ""
        self._session_entry_generation = 0
        self._session_entry_request_seq: dict[str, int] = {}
        self._disposed = False
        self._active_session_read_only = False
        self._active_session_projection = ActiveSessionProjection(
            key="",
            message_count=None,
            has_messages=None,
            read_only=False,
        )

        self._bootstrapResult.connect(self._handle_bootstrap_result)
        self._listResult.connect(self._handle_list_result)
        self._selectResult.connect(self._handle_select_result)
        self._createResult.connect(self._handle_create_result)
        self._deleteResult.connect(self._handle_delete_result)
        self._sessionChange.connect(self._handle_session_change)
        self._sessionEntryResult.connect(self._handle_session_entry_result)

    @Property(QObject, constant=True)
    def sessionsModel(self) -> SessionListModel:
        return self._model

    @Property(QObject, constant=True)
    def sidebarModel(self) -> SidebarRowsModel:
        return self._sidebar_model

    @Property(int, notify=sidebarProjectionChanged)
    def sidebarUnreadCount(self) -> int:
        return self._sidebar_unread_count

    @Property(str, notify=sidebarProjectionChanged)
    def sidebarUnreadFingerprint(self) -> str:
        return self._sidebar_unread_fingerprint

    @Property(str, notify=activeKeyChanged)
    def activeKey(self) -> str:
        return self._active_key

    @Property(bool, notify=sessionsLoadingChanged)
    def sessionsLoading(self) -> bool:
        return self._sessions_loading

    @Property(bool, notify=activeSessionMetaChanged)
    def activeSessionReadOnly(self) -> bool:
        return self._active_session_read_only

    def supervisorSessionsSnapshot(self) -> list[dict[str, Any]]:
        return [
            dict(item)
            for item in getattr(self._model, "_sessions", [])
            if isinstance(item, dict)
        ]

    def initialize(self, session_manager: Any) -> None:
        if self._disposed:
            return
        if self._session_manager is session_manager:
            return
        self._attach_session_manager(session_manager)
        self.refresh()

    @Slot(str)
    def bootstrapWorkspace(self, workspace_path: str) -> None:
        self.bootstrapStorageRoot(workspace_path)

    @Slot(str)
    def bootstrapStorageRoot(self, storage_root: str) -> None:
        if self._disposed:
            return
        raw_path = storage_root.strip()
        if not raw_path:
            return
        current = getattr(self._session_manager, "workspace", None)
        if current is not None and str(Path(str(current)).expanduser()) == str(
            Path(raw_path).expanduser()
        ):
            self.refresh()
            return
        self._set_sessions_loading(True)
        self._bootstrap_storage_root = str(Path(raw_path).expanduser())
        fut = self._submit_safe(self._create_session_manager(raw_path))
        if fut is None:
            self._set_sessions_loading(False)
            return
        fut.add_done_callback(self._on_bootstrap_done)

    @Slot()
    def shutdown(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        self._pending_select_key = None
        self._pending_deletes.clear()
        self._pending_creates.clear()
        self._session_entry_request_seq.clear()
        self._list_inflight_count = 0
        self._set_sessions_loading(False)
        self._sidebar_expanded_groups = {}
        self._sidebar_model.clear_rows()
        self._set_sidebar_unread_summary(0, "")
        self._set_active_session_projection("")
        self._detach_session_manager(self._session_manager)
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

    async def _run_bg_io(self, fn: Any, *args: Any) -> Any:
        if isinstance(self._runner, AsyncioRunner):
            return await self._runner.run_bg_io(fn, *args)
        return await asyncio.to_thread(fn, *args)

    async def _create_session_manager(self, storage_root: str) -> Any:
        from bao.session.manager import SessionManager

        root = Path(storage_root).expanduser()
        await self._run_user_io(lambda: root.mkdir(parents=True, exist_ok=True))
        return await self._run_user_io(SessionManager, root)

    def _on_bootstrap_done(self, future: Any) -> None:
        if future.cancelled():
            return
        exc = future.exception()
        if exc:
            self._bootstrapResult.emit(False, str(exc), None)
            return
        self._bootstrapResult.emit(True, "", future.result())

    async def _backfill_listed_session_tails(self, keys: list[str]) -> None:
        sm = self._session_manager
        if sm is None or not keys:
            return
        backfill = getattr(sm, "backfill_display_tail_rows", None)
        if not callable(backfill):
            return
        await self._run_bg_io(backfill, keys, 200)

    def _on_backfill_done(self, future: Any) -> None:
        if future.cancelled():
            return
        exc = self._future_exception_or_none(future)
        if exc is not None:
            logger.debug("Skip display tail backfill: {}", exc)

    def _handle_bootstrap_result(self, ok: bool, error: str, session_manager: Any) -> None:
        if not ok:
            self._set_sessions_loading(False)
            logger.debug("Skip early session bootstrap: {}", error)
            return
        if self._disposed:
            return
        expected_root = self._bootstrap_storage_root
        actual_root = str(Path(str(getattr(session_manager, "workspace", ""))).expanduser())
        if expected_root and actual_root and expected_root != actual_root:
            return
        self.initialize(session_manager)
        self.sessionManagerReady.emit(session_manager)

    def _attach_session_manager(self, session_manager: Any) -> None:
        previous = self._session_manager
        if previous is session_manager:
            return
        self._detach_session_manager(previous)
        self._session_manager = session_manager
        add_listener = getattr(session_manager, "add_change_listener", None)
        if callable(add_listener):
            add_listener(self._on_session_change)

    def _detach_session_manager(self, session_manager: Any) -> None:
        if session_manager is None:
            return
        remove_listener = getattr(session_manager, "remove_change_listener", None)
        if callable(remove_listener):
            try:
                remove_listener(self._on_session_change)
            except Exception as exc:
                logger.debug("Skip session listener removal: {}", exc)

    def _emit_active_key_if_changed(self, new_key: str) -> None:
        """Emit activeKeyChanged only if key actually changed."""
        if new_key != self._last_emitted_active_key:
            self._last_emitted_active_key = new_key
            self.activeKeyChanged.emit(new_key)
            self._emit_active_ready_if_applicable(new_key)

    def _session_item_by_key(self, key: str) -> dict[str, Any] | None:
        if not key:
            return None
        for session in self._model._sessions:
            if str(session.get("key", "")) == key:
                return session
        return None

    def _set_active_session_projection(self, key: str) -> None:
        projection = project_active_session(self._model._sessions, key)
        self._active_session_projection = projection
        if self._active_session_read_only == projection.read_only:
            return
        self._active_session_read_only = projection.read_only
        self.activeSessionMetaChanged.emit()

    def _is_read_only_session(self, key: str) -> bool:
        session = self._session_item_by_key(key)
        return bool(session.get("is_read_only", False)) if session is not None else False

    def _emit_active_summary(self, key: str) -> None:
        self._set_active_session_projection(key)
        projection = self._active_session_projection
        self.activeSummaryChanged.emit(key, projection.message_count, projection.has_messages)

    def _rebuild_sidebar_projection(self, channels: set[str] | None = None) -> None:
        self.sidebarProjectionWillChange.emit()
        projection = build_sidebar_projection(
            self._model._sessions,
            active_key=self._active_key,
            expanded_groups=self._sidebar_expanded_groups,
            current_rows=self._sidebar_model._rows,
            channels=channels,
        )
        self._sidebar_expanded_groups = projection.expanded_groups
        self._sidebar_model.sync_rows(projection.rows)
        self._set_sidebar_unread_summary(
            projection.unread_count,
            projection.unread_fingerprint,
        )
        self.sidebarProjectionChanged.emit()

    def _apply_session_view(
        self,
        sessions: list[dict[str, Any]],
        active_for_view: str,
        *,
        sidebar_channels: set[str] | None = None,
        backfill_keys: list[str] | None = None,
    ) -> None:
        self._commit_session_view(
            sessions,
            active_for_view,
            model_apply=self._model.sync_sessions,
            sidebar_channels=sidebar_channels,
            backfill_keys=backfill_keys,
            derive_backfill_keys=backfill_keys is None,
        )

    def _apply_incremental_session_updates(
        self,
        sessions: list[dict[str, Any]],
        active_for_view: str,
        *,
        sidebar_channels: set[str] | None = None,
        backfill_keys: list[str] | None = None,
    ) -> None:
        self._commit_session_view(
            sessions,
            active_for_view,
            model_apply=self._model.upsert_sessions,
            sidebar_channels=sidebar_channels,
            backfill_keys=backfill_keys,
        )

    def _set_sessions_loading(self, loading: bool) -> None:
        if self._sessions_loading == loading:
            return
        self._sessions_loading = loading
        self.sessionsLoadingChanged.emit(loading)

    def _begin_list_request(self) -> None:
        self._list_inflight_count += 1
        self._set_sessions_loading(True)

    def _finish_list_request(self) -> None:
        self._list_inflight_count = max(0, self._list_inflight_count - 1)
        self._set_sessions_loading(self._list_inflight_count > 0)

    def _next_active_commit_seq(self) -> int:
        self._active_commit_seq += 1
        return self._active_commit_seq

    def _set_sidebar_unread_summary(self, unread_count: int, unread_fingerprint: str) -> None:
        self._sidebar_unread_count = unread_count
        self._sidebar_unread_fingerprint = unread_fingerprint

    @staticmethod
    def _with_active_session_read(
        sessions: list[dict[str, Any]],
        active_for_view: str,
    ) -> list[dict[str, Any]]:
        next_sessions = [dict(item) for item in sessions]
        for item in next_sessions:
            if str(item.get("key", "")) == active_for_view:
                item["has_unread"] = False
        return next_sessions

    def _schedule_tail_backfill(self, backfill_keys: list[str]) -> None:
        if not backfill_keys:
            return
        fut = self._submit_safe(
            self._backfill_listed_session_tails(list(dict.fromkeys(backfill_keys)))
        )
        if fut is not None:
            fut.add_done_callback(self._on_backfill_done)

    def _commit_session_view(
        self,
        sessions: list[dict[str, Any]],
        active_for_view: str,
        *,
        model_apply: Any,
        sidebar_channels: set[str] | None = None,
        backfill_keys: list[str] | None = None,
        derive_backfill_keys: bool = False,
        emit_sessions_changed: bool = True,
    ) -> None:
        next_sessions = self._with_active_session_read(sessions, active_for_view)
        model_apply(next_sessions, active_for_view)
        self._commit_active_view(
            active_for_view,
            sidebar_channels=sidebar_channels,
            emit_sessions_changed=emit_sessions_changed,
        )
        target_backfill_keys = (
            tail_backfill_keys(next_sessions) if derive_backfill_keys else list(backfill_keys or [])
        )
        self._schedule_tail_backfill(target_backfill_keys)

    def _replace_session_view(
        self,
        sessions: list[dict[str, Any]],
        active_for_view: str,
        *,
        sidebar_channels: set[str] | None = None,
        backfill_keys: list[str] | None = None,
        derive_backfill_keys: bool = False,
    ) -> None:
        self._commit_session_view(
            sessions,
            active_for_view,
            model_apply=self._model.reset_sessions,
            sidebar_channels=sidebar_channels,
            backfill_keys=backfill_keys,
            derive_backfill_keys=derive_backfill_keys,
        )

    def _commit_active_view(
        self,
        key: str,
        *,
        sidebar_channels: set[str] | None = None,
        emit_sessions_changed: bool,
    ) -> None:
        self._active_key = key
        self._rebuild_sidebar_projection(sidebar_channels)
        if emit_sessions_changed:
            self.sessionsChanged.emit()
        self._emit_active_summary(key)
        self._emit_active_key_if_changed(key)

    def _set_local_active_key(self, key: str) -> None:
        if self._active_key == key:
            return
        self._model.set_active(key)
        if _DEBUG_SWITCH:
            logger.debug("session_select_commit key={}", key)
        self._commit_active_view(key, emit_sessions_changed=False)

    def _finalize_active_resolution(self, active_for_view: str) -> None:
        self._clear_pending_select_if_resolved(active_for_view)

    def _desktop_startup_target_key(self) -> str:
        active_key = self._active_key
        if active_key and session_channel_key(active_key) == "desktop":
            for session in self._model._sessions:
                if str(session.get("key", "")) == active_key:
                    return active_key
        for session in self._model._sessions:
            key = str(session.get("key", ""))
            if session_channel_key(key) == "desktop":
                return key
        return ""

    def _emit_active_ready_if_applicable(self, key: str) -> None:
        if self._gateway_ready and key:
            self.activeReady.emit(key)

    def _emit_startup_target_if_applicable(self) -> None:
        if not self._gateway_ready:
            return
        target_key = self._desktop_startup_target_key()
        if target_key:
            self.startupTargetReady.emit(target_key)

    def _on_session_change(self, event: SessionChangeEvent) -> None:
        self._sessionChange.emit(event)

    def _handle_session_change(self, event: object) -> None:
        if self._disposed or not isinstance(event, SessionChangeEvent):
            return
        if event.session_key in self._pending_deletes:
            return
        if event.kind in {"metadata", "messages"}:
            load_entry = getattr(self._session_manager, "get_session_list_entry", None)
            if callable(load_entry):
                request_seq = self._session_entry_request_seq.get(event.session_key, 0) + 1
                self._session_entry_request_seq[event.session_key] = request_seq
                fut = self._submit_safe(
                    self._load_session_entry(
                        event.session_key,
                        request_seq=request_seq,
                        generation=self._session_entry_generation,
                    )
                )
                if fut is not None:
                    fut.add_done_callback(self._on_session_entry_done)
                    return
        self.refresh()

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
        self._session_entry_generation += 1
        self._begin_list_request()
        self._list_request_seq += 1
        seq = self._list_request_seq
        self._list_latest_seq = seq
        fut = self._submit_safe(self._list_sessions(seq))
        if fut is None:
            self._finish_list_request()
            return
        fut.add_done_callback(self._on_list_done)

    @Slot()
    def setGatewayReady(self) -> None:
        self._gateway_ready = True
        if self._active_key:
            self._emit_active_ready_if_applicable(self._active_key)
        self._emit_startup_target_if_applicable()

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
            build_session_item(key, natural_key=self._natural_key),
            *sessions_before,
        ]

        self._gateway_ready = True
        self._pending_select_key = key
        self._replace_session_view(sessions_after, key)

        fut = self._submit_safe(self._create_session(key, self._next_active_commit_seq()))
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
        self._set_local_active_key(key)
        fut = self._submit_safe(self._select_session(key, self._next_active_commit_seq()))
        if fut is None:
            return
        fut.add_done_callback(self._on_select_done)

    @Slot(str)
    def deleteSession(self, key: str) -> None:
        if self._disposed:
            return
        if not key or self._session_manager is None or key in self._pending_deletes:
            return
        if self._is_read_only_session(key):
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
            sessions_after = [build_session_item(new_active, natural_key=self._natural_key)]
            create_seq = self._next_active_commit_seq()
            fut_create = self._submit_safe(self._create_session(new_active, create_seq))
            if fut_create is not None:
                fut_create.add_done_callback(
                    lambda future, k=new_active: self._on_create_done(k, future)
                )
        elif active_before == key:
            new_active = pick_latest_key(
                sessions_after,
                preferred_channel=(removed_channel or "desktop"),
            )

        for item in sessions_after:
            if str(item.get("key", "")) == new_active:
                item["has_unread"] = False

        self._pending_deletes[key] = (
            sessions_before,
            active_before,
            new_active,
            dict(self._sidebar_expanded_groups),
        )
        self._replace_session_view(sessions_after, new_active)

        delete_seq = self._next_active_commit_seq() if active_before == key else None
        fut = self._submit_safe(self._delete_session(key, new_active, delete_seq))
        if fut is None:
            self._pending_deletes.pop(key, None)
            return
        fut.add_done_callback(lambda future, k=key: self._on_delete_done(k, future))

    @Slot(str)
    def toggleSidebarGroup(self, channel: str) -> None:
        if not channel:
            return
        expanded = self._sidebar_expanded_groups.get(channel, False) is True
        self._sidebar_expanded_groups[channel] = not expanded
        self._rebuild_sidebar_projection()

    # ------------------------------------------------------------------
    # Async helpers (run on asyncio thread)
    # ------------------------------------------------------------------

    async def _list_sessions(self, seq: int) -> tuple[int, list[dict[str, Any]], str]:
        sm = self._session_manager
        raw_sessions = await self._run_user_io(sm.list_sessions)
        active_raw = await self._run_user_io(sm.get_active_session_key, self._natural_key)
        active = active_raw or ""
        result = [
            project_session_item(
                session,
                natural_key=self._natural_key,
                current_sessions=[],
            )
            for session in raw_sessions
        ]
        return seq, normalize_session_items(result), active

    async def _load_session_entry(
        self,
        key: str,
        *,
        request_seq: int,
        generation: int,
    ) -> tuple[str, int, int, dict[str, Any] | None]:
        sm = self._session_manager
        load_entry = getattr(sm, "get_session_list_entry", None)
        if not callable(load_entry):
            return key, request_seq, generation, None
        entry = await self._run_user_io(load_entry, key)
        return key, request_seq, generation, entry

    async def _commit_active_selection(self, key: str, seq: int) -> None:
        sm = self._session_manager
        if sm is None or not key:
            return

        def _write() -> None:
            if seq != self._active_commit_seq:
                return
            sm.set_active_session_key(self._natural_key, key)

        await self._run_user_io(_write)

    async def _clear_active_selection(self, seq: int) -> None:
        sm = self._session_manager
        if sm is None:
            return

        def _clear() -> None:
            if seq != self._active_commit_seq:
                return
            sm.clear_active_session_key(self._natural_key)

        await self._run_user_io(_clear)

    def _build_new_session_key(self, name: str) -> str:
        if name:
            return f"{self._natural_key}::{name}"
        import time

        return f"{self._natural_key}::session-{int(time.time())}"

    async def _create_session(self, key: str, seq: int) -> str:
        sm = self._session_manager

        def _create() -> None:
            session = sm.get_or_create(key)
            sm.save(session)

        await self._run_user_io(_create)
        await self._commit_active_selection(key, seq)
        return key

    async def _select_session(self, key: str, seq: int) -> str:
        await self._commit_active_selection(key, seq)
        return key

    async def _delete_session(self, key: str, new_active: str, seq: int | None) -> str:
        sm = self._session_manager

        def _delete() -> bool:
            was_active = sm.get_active_session_key(self._natural_key) == key
            delete_fn = getattr(sm, "delete_session_tree", sm.delete_session)
            deleted = delete_fn(key)
            if not deleted:
                still_exists = True
                try:
                    still_exists = any(s.get("key") == key for s in sm.list_sessions())
                except Exception:
                    still_exists = True
                if still_exists:
                    raise RuntimeError(f"delete session failed: {key}")
            return was_active

        was_active = await self._run_user_io(_delete)
        if not was_active or seq is None:
            return ""
        try:
            if new_active:
                await self._commit_active_selection(new_active, seq)
            else:
                await self._clear_active_selection(seq)
        except Exception as exc:
            logger.warning("Session deleted but active sync failed: {}", exc)
            return str(exc)
        return ""

    # ------------------------------------------------------------------
    # Callbacks (asyncio thread — emit signals only, no Qt ops)
    # ------------------------------------------------------------------

    def _future_exception_or_none(self, future: Any) -> Exception | None:
        try:
            return future.exception()
        except FutureCancelledError:
            return None

    def _on_list_done(self, future: Any) -> None:
        if self._disposed:
            return
        if future.cancelled():
            return
        exc = self._future_exception_or_none(future)
        if exc:
            self._listResult.emit(False, str(exc), None)
        else:
            self._listResult.emit(True, "", future.result())

    def _on_session_entry_done(self, future: Any) -> None:
        if self._disposed:
            return
        if future.cancelled():
            return
        exc = self._future_exception_or_none(future)
        if exc:
            self._sessionEntryResult.emit(False, str(exc), None)
        else:
            self._sessionEntryResult.emit(True, "", future.result())

    def _on_select_done(self, future: Any) -> None:
        if self._disposed:
            return
        if future.cancelled():
            return
        exc = self._future_exception_or_none(future)
        if exc:
            self._selectResult.emit(False, str(exc), "")
        else:
            self._selectResult.emit(True, "", future.result())

    def _on_create_done(self, key: str, future: Any) -> None:
        if self._disposed:
            return
        if future.cancelled():
            return
        exc = self._future_exception_or_none(future)
        if exc:
            self._createResult.emit(False, str(exc), key)
        else:
            self._createResult.emit(True, "", str(future.result() or key))

    def _on_delete_done(self, key: str, future: Any) -> None:
        if self._disposed:
            return
        if future.cancelled():
            return
        exc = self._future_exception_or_none(future)
        if exc:
            self._deleteResult.emit(key, False, str(exc))
        else:
            self._deleteResult.emit(key, True, str(future.result() or ""))

    # ------------------------------------------------------------------
    # Main-thread handlers (connected via signals)
    # ------------------------------------------------------------------

    def _handle_list_result(self, ok: bool, error: str, data: Any) -> None:
        if self._disposed:
            return
        self._finish_list_request()
        if not ok:
            self.errorOccurred.emit(error)
            return
        seq = 0
        sessions: list[dict[str, Any]]
        stored_active = ""
        if isinstance(data, tuple) and len(data) == 3 and isinstance(data[0], int):
            seq, sessions, active = data
            if seq != self._list_latest_seq:
                return
            if isinstance(active, str):
                stored_active = active
        else:
            if not (isinstance(data, tuple) and len(data) == 2):
                return
            raw_sessions, raw_active = data
            if not isinstance(raw_sessions, list):
                return
            sessions = filter_session_dicts(raw_sessions)
            if isinstance(raw_active, str):
                stored_active = raw_active
        pending_keys = set(self._pending_deletes.keys())
        if pending_keys:
            sessions = [s for s in sessions if s.get("key") not in pending_keys]

        pending_create_keys = set(self._pending_creates)
        if pending_create_keys:
            existing_keys = {str(s.get("key", "")) for s in sessions}
            for key in pending_create_keys:
                if key in existing_keys:
                    continue
                sessions.insert(
                    0,
                    build_session_item(key, natural_key=self._natural_key),
                )
                existing_keys.add(key)

        available_keys = {str(s.get("key", "")) for s in sessions}

        active_for_view = ""
        auto_selected_key = ""
        pending_candidate = visible_session_key(
            (self._pending_select_key or "",),
            available_keys=available_keys,
            pending_create_keys=pending_create_keys,
        )
        local_active_candidate = visible_session_key(
            (self._active_key,),
            available_keys=available_keys,
            pending_create_keys=pending_create_keys,
        )
        stored_active_candidate = visible_session_key_for_channel(
            (stored_active,),
            available_keys=available_keys,
            pending_create_keys=pending_create_keys,
            channel="desktop",
        )

        if pending_candidate:
            active_for_view = pending_candidate
        elif local_active_candidate:
            active_for_view = local_active_candidate
        elif stored_active_candidate:
            active_for_view = stored_active_candidate

        if self._gateway_ready and not sessions and not pending_create_keys:
            if self._session_manager is not None:
                self.newSession("")
                return

        if self._gateway_ready and not self._pending_select_key and not active_for_view:
            if sessions:
                active_for_view = pick_latest_key(sessions, preferred_channel="desktop")
                auto_selected_key = active_for_view
            else:
                if self._session_manager is not None:
                    self.newSession("")
                    return

        if not sessions and self._active_key:
            self._active_key = ""
            self._emit_active_key_if_changed("")

        self._apply_session_view(sessions, active_for_view)
        self._emit_startup_target_if_applicable()
        self._finalize_active_resolution(active_for_view)
        if auto_selected_key and self._session_manager is not None:
            fut = self._submit_safe(
                self._select_session(auto_selected_key, self._next_active_commit_seq())
            )
            if fut is not None:
                fut.add_done_callback(self._on_select_done)


    def _handle_session_entry_result(self, ok: bool, error: str, data: Any) -> None:
        if self._disposed:
            return
        if not ok:
            logger.debug("Skip incremental session update: {}", error)
            self.refresh()
            return
        if not (isinstance(data, tuple) and len(data) == 4):
            self.refresh()
            return
        key, request_seq, generation, entry = data
        if key in self._pending_deletes:
            return
        if generation != self._session_entry_generation:
            return
        if self._session_entry_request_seq.get(key, 0) != request_seq:
            return
        if entry is None or not isinstance(entry, dict):
            self.refresh()
            return
        current_sessions = [dict(item) for item in self._model._sessions]
        current_by_key = {
            str(item.get("key", "")): dict(item)
            for item in current_sessions
            if str(item.get("key", ""))
        }
        old_item = current_by_key.get(str(key))
        projected = project_session_item(
            entry,
            natural_key=self._natural_key,
            current_sessions=current_sessions,
        )
        related_parent_keys = {
            str(parent_key)
            for parent_key in (
                projected.get("parent_session_key", ""),
                old_item.get("parent_session_key", "") if old_item else "",
            )
            if str(parent_key)
        }
        affected_keys = {str(key), *related_parent_keys}
        for item in current_sessions:
            item_key = str(item.get("key", ""))
            parent_key = str(item.get("parent_session_key", ""))
            if parent_key == str(key) or parent_key in related_parent_keys:
                affected_keys.add(item_key)

        updates: dict[str, dict[str, Any]] = {str(key): projected}
        for affected_key in affected_keys:
            if affected_key in updates:
                continue
            existing = current_by_key.get(affected_key)
            if existing is not None:
                updates[affected_key] = dict(existing)

        normalization_source = [
            updates.get(item_key, current_by_key[item_key])
            for item_key in current_by_key
            if item_key in current_by_key
        ]
        normalization_source.extend(
            session for key, session in updates.items() if key not in current_by_key
        )
        title_index = title_by_key(normalization_source)
        running_parent_index = running_parent_keys(normalization_source)
        normalized_updates = [
            normalize_session_item(
                session,
                title_index=title_index,
                running_parent_index=running_parent_index,
            )
            for session in updates.values()
        ]
        sidebar_channels = {
            str(item.get("channel", "other") or "other")
            for item in normalized_updates
            if str(item.get("key", "")) in affected_keys
        }
        if old_item is not None:
            old_channel = str(old_item.get("channel", "other") or "other")
            if old_channel:
                sidebar_channels.add(old_channel)
        backfill_keys = [str(key)] if bool(projected.get("needs_tail_backfill", False)) else []
        available_keys = set(current_by_key)
        available_keys.add(str(key))
        active_for_view = self._active_key if self._active_key in available_keys else ""
        if not active_for_view and normalized_updates and not self._pending_select_key:
            candidate_sessions = [
                current_by_key[item_key]
                for item_key in current_by_key
                if item_key not in updates
            ] + normalized_updates
            active_for_view = pick_latest_key(candidate_sessions, preferred_channel="desktop")
        self._apply_incremental_session_updates(
            normalized_updates,
            active_for_view,
            sidebar_channels=sidebar_channels or None,
            backfill_keys=backfill_keys,
        )
        self._emit_startup_target_if_applicable()

    def _handle_select_result(self, ok: bool, error: str, key: str) -> None:
        if self._disposed:
            return
        if self._pending_select_key is not None and key != self._pending_select_key:
            return
        if self._pending_select_key is None and key != self._active_key:
            if _DEBUG_SWITCH:
                logger.debug(
                    "Ignore stale select result key={} active={} pending=<none>",
                    key,
                    self._active_key,
                )
            return
        if not ok:
            self._pending_select_key = None
            self.errorOccurred.emit(error)
            self.refresh()
            return
        self._set_local_active_key(key)

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
                sessions_before, active_before, optimistic_active, expanded_groups_before = snapshot
                if self._active_key == optimistic_active:
                    pending_keys = set(self._pending_deletes.keys())
                    if pending_keys:
                        sessions_before = [
                            s for s in sessions_before if str(s.get("key", "")) not in pending_keys
                        ]
                        if active_before in pending_keys:
                            active_before = self._active_key
                    self._sidebar_expanded_groups = dict(expanded_groups_before)
                    self._replace_session_view(sessions_before, active_before)
                else:
                    self.refresh()
            self.errorOccurred.emit(error)
            self.deleteCompleted.emit(key, False, error)
            return
        # Optimistic update already reflects correct state — skip refresh
        # to avoid a redundant full rebuild that causes list flicker.
        if error:
            self.refresh()
        self.deleteCompleted.emit(key, True, "")
