"""SessionService — wraps Bao SessionManager for the desktop channel.

All SessionManager calls are dispatched to the asyncio thread via AsyncioRunner.
Internal signals marshal results back to the Qt main thread.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from concurrent.futures import CancelledError as FutureCancelledError
from datetime import datetime
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

from app.backend.asyncio_runner import AsyncioRunner
from bao.session.manager import SessionChangeEvent

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


def _session_family_key(key: str) -> str:
    if "::" in key:
        prefix, _sep, _suffix = key.partition("::")
        return prefix
    return key


def _session_channel_key(key: str) -> str:
    family = _session_family_key(key)
    if ":" in family:
        prefix, _sep, _rest = family.partition(":")
        return prefix or "other"
    return family if family == "heartbeat" else "other"


def _parse_updated_at(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw <= 0:
            return None
        if raw > 10_000_000_000:
            raw /= 1000.0
        try:
            return datetime.fromtimestamp(raw)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            return _parse_updated_at(int(raw))
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _format_updated_label(updated: Any) -> str:
    dt = _parse_updated_at(updated)
    if dt is None:
        return ""

    now = datetime.now(tz=dt.tzinfo)
    seconds = max(0, int((now - dt).total_seconds()))
    if seconds < 60:
        return "<1m"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    if seconds < 604800:
        return f"{seconds // 86400}d"
    if dt.year == now.year:
        return f"{dt.month}/{dt.day}"
    return f"{dt.year}/{dt.month}/{dt.day}"


def _build_session_item(
    key: str,
    *,
    natural_key: str,
    updated_at: Any = "",
    channel: str = "desktop",
    has_unread: bool = False,
    title: Any = None,
    message_count: Any = None,
    has_messages: Any = None,
    session_kind: str = "regular",
    read_only: bool = False,
    parent_session_key: str = "",
    parent_title: str = "",
    child_status: str = "",
    is_running: bool = False,
) -> dict[str, Any]:
    normalized_count = (
        message_count if isinstance(message_count, int) and message_count >= 0 else None
    )
    normalized_has_messages = (
        has_messages
        if isinstance(has_messages, bool)
        else (normalized_count > 0 if normalized_count is not None else None)
    )
    return {
        "key": key,
        "title": _format_display_title(key, title, natural_key=natural_key),
        "updated_at": updated_at,
        "updated_label": _format_updated_label(updated_at),
        "channel": channel,
        "has_unread": has_unread,
        "message_count": normalized_count,
        "has_messages": normalized_has_messages,
        "session_kind": session_kind,
        "is_read_only": read_only,
        "parent_session_key": parent_session_key,
        "parent_title": parent_title,
        "child_status": child_status,
        "is_running": is_running,
    }


def _filter_session_dicts(raw_sessions: list[Any]) -> list[dict[str, Any]]:
    return [item for item in raw_sessions if isinstance(item, dict)]


def _visible_session_key(
    candidates: tuple[str, ...],
    *,
    available_keys: set[str],
    pending_create_keys: set[str],
) -> str:
    for candidate in candidates:
        if candidate and (candidate in pending_create_keys or candidate in available_keys):
            return candidate
    return ""


def _visible_session_key_for_channel(
    candidates: tuple[str, ...],
    *,
    available_keys: set[str],
    pending_create_keys: set[str],
    channel: str,
) -> str:
    for candidate in candidates:
        if not candidate:
            continue
        if candidate not in pending_create_keys and candidate not in available_keys:
            continue
        if _session_channel_key(candidate) != channel:
            continue
        return candidate
    return ""


def _sidebar_channel_sort_key(channel: str) -> tuple[int, str]:
    if channel == "desktop":
        return (0, channel)
    if channel == "heartbeat":
        return (2, channel)
    return (1, channel)


def _visible_sidebar_items(
    items: list[dict[str, Any]], *, expanded: bool, active_key: str
) -> list[dict[str, Any]]:
    if expanded:
        return items
    if not active_key:
        return []
    return [item for item in items if str(item.get("key", "")) == active_key]


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
        self._sessions = sessions
        self._active_key = active_key
        self.endResetModel()

    def set_active(self, key: str) -> None:
        if self._active_key == key:
            return
        old_key = self._active_key
        self._active_key = key
        for i, s in enumerate(self._sessions):
            session_key = s.get("key")
            if session_key == key and s.get("has_unread"):
                s["has_unread"] = False
            if session_key in (old_key, key):
                idx = self.index(i)
                self.dataChanged.emit(idx, idx, [_ROLE_IS_ACTIVE, _ROLE_HAS_UNREAD])


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
        self._disposed = False
        self._active_session_read_only = False

        self._bootstrapResult.connect(self._handle_bootstrap_result)
        self._listResult.connect(self._handle_list_result)
        self._selectResult.connect(self._handle_select_result)
        self._createResult.connect(self._handle_create_result)
        self._deleteResult.connect(self._handle_delete_result)
        self._sessionChange.connect(self._handle_session_change)

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

    def initialize(self, session_manager: Any) -> None:
        if self._disposed:
            return
        self._attach_session_manager(session_manager)
        self.refresh()

    @Slot(str)
    def bootstrapWorkspace(self, workspace_path: str) -> None:
        if self._disposed or self._session_manager is not None:
            return
        raw_path = workspace_path.strip()
        if not raw_path:
            return
        self._set_sessions_loading(True)
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
        self._list_inflight_count = 0
        self._set_sessions_loading(False)
        self._sidebar_expanded_groups = {}
        self._sidebar_model.clear_rows()
        self._set_sidebar_unread_summary(0, "")
        self._refresh_active_session_meta("")
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

    async def _create_session_manager(self, workspace_path: str) -> Any:
        from bao.session.manager import SessionManager

        workspace = Path(workspace_path).expanduser()
        await self._run_user_io(lambda: workspace.mkdir(parents=True, exist_ok=True))
        return await self._run_user_io(SessionManager, workspace)

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
        if self._disposed or self._session_manager is not None:
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

    def _active_summary(self, key: str) -> tuple[int | None, bool | None]:
        if not key:
            return None, None
        for session in self._model._sessions:
            if str(session.get("key", "")) != key:
                continue
            message_count = session.get("message_count")
            has_messages = session.get("has_messages")
            return (
                message_count if isinstance(message_count, int) and message_count >= 0 else None,
                has_messages if isinstance(has_messages, bool) else None,
            )
        return None, None

    def _refresh_active_session_meta(self, key: str) -> None:
        read_only = False
        for session in self._model._sessions:
            session_key = str(session.get("key", ""))
            if session_key == key:
                read_only = bool(session.get("is_read_only", False))
                break
        if self._active_session_read_only == read_only:
            return
        self._active_session_read_only = read_only
        self.activeSessionMetaChanged.emit()

    def _is_read_only_session(self, key: str) -> bool:
        if not key:
            return False
        for session in self._model._sessions:
            if str(session.get("key", "")) != key:
                continue
            return bool(session.get("is_read_only", False))
        return False

    def _emit_active_summary(self, key: str) -> None:
        message_count, has_messages = self._active_summary(key)
        self.activeSummaryChanged.emit(key, message_count, has_messages)
        self._refresh_active_session_meta(key)

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

    def _initial_sidebar_group_expanded(
        self,
        channel: str,
        items: list[dict[str, Any]],
        active_key: str,
    ) -> bool:
        if active_key and any(str(item.get("key", "")) == active_key for item in items):
            return True
        if active_key:
            return False
        return channel == "desktop"

    def _pin_sidebar_active_row(self, rows: list[dict[str, Any]]) -> None:
        active_key = self._active_key
        if not active_key:
            return
        current_active_index = self._sidebar_model.active_row_index(active_key)
        if current_active_index < 0:
            return
        current_rows = self._sidebar_model._rows
        if current_active_index >= len(current_rows):
            return
        current_active_row = current_rows[current_active_index]
        active_channel = str(current_active_row.get("channel", "") or "")
        if not active_channel:
            return
        session_slot = 0
        for index in range(current_active_index - 1, -1, -1):
            row = current_rows[index]
            row_channel = str(row.get("channel", "") or "")
            if row_channel != active_channel:
                continue
            if bool(row.get("is_header", False)):
                break
            session_slot += 1
        next_active_index = -1
        for idx, row in enumerate(rows):
            if str(row.get("item_key", "")) != active_key:
                continue
            next_active_index = idx
            break
        if next_active_index < 0 or next_active_index == current_active_index:
            return
        pinned_row = rows.pop(next_active_index)
        header_index = -1
        session_count = 0
        for idx, row in enumerate(rows):
            row_channel = str(row.get("channel", "") or "")
            if row_channel != active_channel:
                continue
            if bool(row.get("is_header", False)):
                header_index = idx
                continue
            if header_index >= 0:
                session_count += 1
        if header_index < 0:
            rows.insert(max(0, min(current_active_index, len(rows))), pinned_row)
            return
        target_index = header_index + 1 + min(session_slot, session_count)
        rows.insert(target_index, pinned_row)

    def _rebuild_sidebar_projection(self) -> None:
        self.sidebarProjectionWillChange.emit()
        groups: dict[str, list[dict[str, Any]]] = {}
        order: list[str] = []
        unread_fingerprint_parts: list[str] = []
        active_key = self._active_key
        available_channels: set[str] = set()

        for session in self._model._sessions:
            key = str(session.get("key", ""))
            title = str(session.get("title", "") or key)
            channel = str(session.get("channel", "other") or "other")
            has_unread = bool(session.get("has_unread", False)) and key != active_key
            updated_text = str(session.get("updated_label", "") or "")
            session_kind = str(session.get("session_kind", "regular") or "regular")
            is_read_only = bool(session.get("is_read_only", False))
            parent_session_key = str(session.get("parent_session_key", "") or "")
            is_running = bool(session.get("is_running", False))
            visual_channel = "subagent" if session_kind == "subagent_child" else channel
            if channel not in groups:
                groups[channel] = []
                order.append(channel)
            groups[channel].append(
                {
                    "key": key,
                    "title": title,
                    "channel": channel,
                    "visual_channel": visual_channel,
                    "has_unread": has_unread,
                    "updated_text": updated_text,
                    "is_read_only": is_read_only,
                    "is_running": is_running,
                    "parent_session_key": parent_session_key,
                    "is_child_session": session_kind == "subagent_child",
                }
            )
            available_channels.add(channel)
            if has_unread:
                unread_fingerprint_parts.append(key)

        self._sidebar_expanded_groups = {
            channel: expanded
            for channel, expanded in self._sidebar_expanded_groups.items()
            if channel in available_channels
        }
        order.sort(key=_sidebar_channel_sort_key)
        for channel in order:
            if channel in self._sidebar_expanded_groups:
                continue
            self._sidebar_expanded_groups[channel] = self._initial_sidebar_group_expanded(
                channel,
                groups[channel],
                active_key,
            )

        rows: list[dict[str, Any]] = []
        for channel in order:
            items = groups[channel]
            expanded = self._sidebar_expanded_groups.get(channel, False) is True
            child_buckets: dict[str, list[dict[str, Any]]] = {}
            child_remainder: list[dict[str, Any]] = []
            reordered_items: list[dict[str, Any]] = []
            for item in items:
                if bool(item.get("is_child_session", False)) and str(
                    item.get("parent_session_key", "")
                ):
                    parent_key = str(item.get("parent_session_key", ""))
                    child_buckets.setdefault(parent_key, []).append(item)
                elif bool(item.get("is_child_session", False)):
                    child_remainder.append(item)
            for item in items:
                if bool(item.get("is_child_session", False)):
                    continue
                reordered_items.append(item)
                reordered_items.extend(child_buckets.get(str(item.get("key", "")), []))
            reordered_items.extend(child_remainder)

            unread_in_group = sum(
                1 for item in reordered_items if bool(item.get("has_unread", False))
            )
            group_has_running = any(bool(item.get("is_running", False)) for item in reordered_items)
            rows.append(
                {
                    "row_id": f"header:{channel}",
                    "is_header": True,
                    "channel": channel,
                    "expanded": expanded,
                    "item_key": "",
                    "item_title": "",
                    "item_updated_text": "",
                    "visual_channel": channel,
                    "is_read_only": False,
                    "is_running": False,
                    "is_child_session": False,
                    "parent_session_key": "",
                    "item_has_unread": False,
                    "item_count": len(reordered_items),
                    "group_unread_count": unread_in_group,
                    "group_has_running": group_has_running,
                    "is_last_in_group": False,
                    "is_first_in_group": False,
                }
            )
            visible_items = _visible_sidebar_items(
                reordered_items,
                expanded=expanded,
                active_key=active_key,
            )
            for index, item in enumerate(visible_items):
                rows.append(
                    {
                        "row_id": f"session:{item.get('key', '')}",
                        "is_header": False,
                        "channel": channel,
                        "expanded": False,
                        "item_key": str(item.get("key", "")),
                        "item_title": str(item.get("title", "") or item.get("key", "")),
                        "item_updated_text": str(item.get("updated_text", "") or ""),
                        "visual_channel": str(item.get("visual_channel", channel) or channel),
                        "is_read_only": bool(item.get("is_read_only", False)),
                        "is_running": bool(item.get("is_running", False)),
                        "is_child_session": bool(item.get("is_child_session", False)),
                        "parent_session_key": str(item.get("parent_session_key", "") or ""),
                        "item_has_unread": bool(item.get("has_unread", False)),
                        "item_count": 0,
                        "group_unread_count": 0,
                        "group_has_running": False,
                        "is_last_in_group": index == len(visible_items) - 1,
                        "is_first_in_group": index == 0,
                    }
                )

        self._pin_sidebar_active_row(rows)
        unread_fingerprint_parts.sort()
        self._sidebar_model.sync_rows(rows)
        self._set_sidebar_unread_summary(
            len(unread_fingerprint_parts),
            "|".join(unread_fingerprint_parts),
        )
        self.sidebarProjectionChanged.emit()

    def _set_local_active_key(self, key: str) -> None:
        if self._active_key == key:
            return
        self._active_key = key
        self._model.set_active(key)
        self._rebuild_sidebar_projection()
        if _DEBUG_SWITCH:
            logger.debug("session_select_commit key={}", key)
        self._emit_active_summary(key)
        self._emit_active_key_if_changed(key)

    def _finalize_active_resolution(self, active_for_view: str) -> None:
        self._clear_pending_select_if_resolved(active_for_view)

    def _desktop_startup_target_key(self) -> str:
        active_key = self._active_key
        if active_key and _session_channel_key(active_key) == "desktop":
            for session in self._model._sessions:
                if str(session.get("key", "")) == active_key:
                    return active_key
        for session in self._model._sessions:
            key = str(session.get("key", ""))
            if _session_channel_key(key) == "desktop":
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
        if event.kind == "deleted" and event.session_key in self._pending_deletes:
            return
        self.refresh()

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
            _build_session_item(key, natural_key=self._natural_key),
            *sessions_before,
        ]

        self._gateway_ready = True
        self._pending_select_key = key
        self._set_local_active_key(key)
        self._model.reset_sessions(sessions_after, key)
        self._rebuild_sidebar_projection()
        self.sessionsChanged.emit()

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
            sessions_after = [_build_session_item(new_active, natural_key=self._natural_key)]
            create_seq = self._next_active_commit_seq()
            fut_create = self._submit_safe(self._create_session(new_active, create_seq))
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

        self._pending_deletes[key] = (
            sessions_before,
            active_before,
            new_active,
            dict(self._sidebar_expanded_groups),
        )
        self._active_key = new_active
        self._model.reset_sessions(sessions_after, new_active)
        self._rebuild_sidebar_projection()
        self.sessionsChanged.emit()
        self._emit_active_key_if_changed(new_active)

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
        sessions = await self._run_user_io(sm.list_sessions)
        active_raw = await self._run_user_io(sm.get_active_session_key, self._natural_key)
        active = active_raw or ""
        title_by_key: dict[str, str] = {}
        parents_with_running_children: set[str] = set()
        for session in sessions:
            key = str(session.get("key") or "")
            meta = session.get("metadata")
            title_by_key[key] = _format_display_title(
                key,
                meta.get("title") if isinstance(meta, dict) else None,
                natural_key=self._natural_key,
            )
            if not isinstance(meta, dict):
                continue
            if str(meta.get("child_status") or "") != "running":
                continue
            parent_key = str(meta.get("parent_session_key") or "")
            if parent_key:
                parents_with_running_children.add(parent_key)
        result = []
        for s in sessions:
            key = s["key"]
            meta = s.get("metadata", {})
            session_kind = str(meta.get("session_kind") or "regular")
            read_only = bool(meta.get("read_only", False))
            parent_session_key = str(meta.get("parent_session_key") or "")
            child_status = str(meta.get("child_status") or "")
            is_running = (
                bool(meta.get("session_running", False))
                or child_status == "running"
                or key in parents_with_running_children
            )
            channel = (
                _session_channel_key(parent_session_key)
                if session_kind == "subagent_child" and parent_session_key
                else _session_channel_key(key)
            )
            last_ai = meta.get("desktop_last_ai_at")
            last_seen_ai = meta.get("desktop_last_seen_ai_at")
            has_unread = False
            if isinstance(last_ai, str) and last_ai:
                seen_ai = (
                    last_seen_ai if isinstance(last_seen_ai, str) and last_seen_ai else last_ai
                )
                has_unread = seen_ai < last_ai
            result.append(
                _build_session_item(
                    key,
                    natural_key=self._natural_key,
                    updated_at=s.get("updated_at", ""),
                    channel=channel,
                    has_unread=has_unread,
                    title=meta.get("title"),
                    message_count=s.get("message_count"),
                    has_messages=s.get("has_messages"),
                    session_kind=session_kind,
                    read_only=read_only,
                    parent_session_key=parent_session_key,
                    parent_title=title_by_key.get(parent_session_key, ""),
                    child_status=child_status,
                    is_running=is_running,
                )
            )
        return seq, result, active

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
            sessions = _filter_session_dicts(raw_sessions)
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
                    _build_session_item(key, natural_key=self._natural_key),
                )
                existing_keys.add(key)

        available_keys = {str(s.get("key", "")) for s in sessions}

        active_for_view = ""
        auto_selected_key = ""
        pending_candidate = _visible_session_key(
            (self._pending_select_key or "",),
            available_keys=available_keys,
            pending_create_keys=pending_create_keys,
        )
        local_active_candidate = _visible_session_key(
            (self._active_key,),
            available_keys=available_keys,
            pending_create_keys=pending_create_keys,
        )
        stored_active_candidate = _visible_session_key_for_channel(
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
                active_for_view = self._pick_latest_key(sessions, preferred_channel="desktop")
                auto_selected_key = active_for_view
            else:
                if self._session_manager is not None:
                    self.newSession("")
                    return

        if not sessions and self._active_key:
            self._active_key = ""
            self._emit_active_key_if_changed("")

        for item in sessions:
            if str(item.get("key", "")) == active_for_view:
                item["has_unread"] = False
        self._active_key = active_for_view
        self._model.reset_sessions(sessions, active_for_view)
        self._rebuild_sidebar_projection()
        self.sessionsChanged.emit()
        self._emit_active_summary(active_for_view)
        fut = self._submit_safe(
            self._backfill_listed_session_tails(
                [str(item.get("key", "")).strip() for item in sessions]
            )
        )
        if fut is not None:
            fut.add_done_callback(self._on_backfill_done)
        self._emit_active_key_if_changed(active_for_view)
        self._emit_startup_target_if_applicable()
        self._finalize_active_resolution(active_for_view)
        if auto_selected_key and self._session_manager is not None:
            fut = self._submit_safe(
                self._select_session(auto_selected_key, self._next_active_commit_seq())
            )
            if fut is not None:
                fut.add_done_callback(self._on_select_done)

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
                    self._active_key = active_before
                    self._sidebar_expanded_groups = dict(expanded_groups_before)
                    for item in sessions_before:
                        if str(item.get("key", "")) == active_before:
                            item["has_unread"] = False
                    self._model.reset_sessions(sessions_before, active_before)
                    self._rebuild_sidebar_projection()
                    self.sessionsChanged.emit()
                    self._emit_active_key_if_changed(active_before)
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
