# ruff: noqa: E402, N802, N815, F403, F405, I001
from __future__ import annotations

from tests._chat_view_integration_shared import *

class EmptyMessagesModel(QAbstractListModel):
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0

    def data(
        self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)
    ) -> object | None:
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {}


class SessionsModel(QAbstractListModel):
    KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 1
    TITLE_ROLE = int(Qt.ItemDataRole.UserRole) + 2
    UPDATED_AT_ROLE = int(Qt.ItemDataRole.UserRole) + 4
    CHANNEL_ROLE = int(Qt.ItemDataRole.UserRole) + 5
    HAS_UNREAD_ROLE = int(Qt.ItemDataRole.UserRole) + 6
    UPDATED_LABEL_ROLE = int(Qt.ItemDataRole.UserRole) + 7

    def __init__(self, rows: list[dict[str, object]], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows = [dict(row) for row in rows]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def data(
        self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)
    ) -> object | None:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        if role == self.KEY_ROLE:
            return row.get("key", "")
        if role == self.TITLE_ROLE:
            return row.get("title", "")
        if role == self.UPDATED_AT_ROLE:
            return row.get("updated_at", "")
        if role == self.CHANNEL_ROLE:
            return row.get("channel", "other")
        if role == self.HAS_UNREAD_ROLE:
            return bool(row.get("has_unread", False))
        if role == self.UPDATED_LABEL_ROLE:
            return row.get("updated_label", "")
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.KEY_ROLE: QByteArray(b"key"),
            self.TITLE_ROLE: QByteArray(b"title"),
            self.UPDATED_AT_ROLE: QByteArray(b"updatedAt"),
            self.CHANNEL_ROLE: QByteArray(b"channel"),
            self.HAS_UNREAD_ROLE: QByteArray(b"hasUnread"),
            self.UPDATED_LABEL_ROLE: QByteArray(b"updatedLabel"),
        }

    def replaceRows(self, rows: list[dict[str, object]]) -> None:
        self.beginResetModel()
        self._rows = [dict(row) for row in rows]
        self.endResetModel()


class DummyChatService(QObject):
    historyLoadingChanged = Signal(bool)
    appendAtBottom = Signal(int)
    statusSettled = Signal(int, str)
    incrementalContent = Signal(int)
    stateChanged = Signal(str)
    hubReady = Signal(bool)
    activeSessionStateChanged = Signal()
    sessionViewApplied = Signal(str)
    historyReady = Signal(str)

    def __init__(self, messages: QAbstractListModel, parent: QObject | None = None, **options: object) -> None:
        super().__init__(parent)
        self._messages = messages
        self._history_loading = False
        self._state = str(options.get("state", "running"))
        self._active_session_ready = bool(options.get("active_session_ready", False))
        self._active_session_has_messages = bool(
            options.get("active_session_has_messages", False)
        )
        self._draft_attachments = EmptyMessagesModel(self)

    @Property(QObject, constant=True)
    def messages(self) -> QObject:
        return self._messages

    @Property(bool, notify=historyLoadingChanged)
    def historyLoading(self) -> bool:
        return self._history_loading

    def setHistoryLoading(self, loading: bool) -> None:
        if self._history_loading == loading:
            return
        self._history_loading = loading
        self.historyLoadingChanged.emit(loading)

    @Property(str, notify=stateChanged)
    def state(self) -> str:
        return self._state

    def setState(self, state: str) -> None:
        if self._state == state:
            return
        self._state = state
        self.stateChanged.emit(state)

    @Property(str, constant=True)
    def lastError(self) -> str:
        return ""

    @Property(str, constant=True)
    def hubDetail(self) -> str:
        return ""

    @Property(bool, constant=True)
    def hubDetailIsError(self) -> bool:
        return False

    @Property(list, constant=True)
    def hubChannels(self) -> list[dict[str, object]]:
        return []

    @Property(bool, notify=activeSessionStateChanged)
    def activeSessionReady(self) -> bool:
        return self._active_session_ready

    @Property(bool, notify=activeSessionStateChanged)
    def activeSessionHasMessages(self) -> bool:
        return self._active_session_has_messages

    @Property(QObject, constant=True)
    def draftAttachments(self) -> QObject:
        return self._draft_attachments

    @Property(int, constant=True)
    def draftAttachmentCount(self) -> int:
        return 0

    def setActiveSessionState(self, ready: bool, has_messages: bool) -> None:
        if (
            self._active_session_ready == ready
            and self._active_session_has_messages == has_messages
        ):
            return
        self._active_session_ready = ready
        self._active_session_has_messages = has_messages
        self.activeSessionStateChanged.emit()

    def emitSessionViewApplied(self, key: str) -> None:
        self.sessionViewApplied.emit(key)
        self.historyReady.emit(key)

    @Slot(str)
    def setLanguage(self, lang: str) -> None:
        _ = lang

    @Slot()
    def start(self) -> None:
        return None

    @Slot()
    def stop(self) -> None:
        return None

    @Slot(str)
    def sendMessage(self, text: str) -> None:
        _ = text

    @Slot("QVariant")
    def addDraftAttachments(self, values: object) -> None:
        _ = values

    @Slot(int)
    def removeDraftAttachment(self, index: int) -> None:
        _ = index

__all__ = [name for name in globals() if name != "__all__" and not (name.startswith("__") and name.endswith("__"))]
