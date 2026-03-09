# ruff: noqa: E402, N802, N815

from __future__ import annotations

import importlib
import sys
from pathlib import Path

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QtGui = pytest.importorskip("PySide6.QtGui")
QtQml = pytest.importorskip("PySide6.QtQml")
QtQuick = pytest.importorskip("PySide6.QtQuick")
QtTest = pytest.importorskip("PySide6.QtTest")

QAbstractListModel = QtCore.QAbstractListModel
QByteArray = QtCore.QByteArray
QEventLoop = QtCore.QEventLoop
QMetaObject = QtCore.QMetaObject
QModelIndex = QtCore.QModelIndex
QObject = QtCore.QObject
QPoint = QtCore.QPoint
QPointF = QtCore.QPointF
Property = QtCore.Property
QQuickItem = QtQuick.QQuickItem
QTimer = QtCore.QTimer
QUrl = QtCore.QUrl
Qt = QtCore.Qt
Signal = QtCore.Signal
Slot = QtCore.Slot
QGuiApplication = QtGui.QGuiApplication
QQmlApplicationEngine = QtQml.QQmlApplicationEngine
QTest = QtTest.QTest

from app.main import WindowFocusDismissFilter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_QML_PATH = PROJECT_ROOT / "app" / "qml" / "Main.qml"


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
    messageAppended = Signal(int)
    statusUpdated = Signal(int, str)
    gatewayReady = Signal(bool)
    activeSessionStateChanged = Signal()
    sessionViewApplied = Signal(str)

    def __init__(
        self,
        messages: QAbstractListModel,
        *,
        state: str = "running",
        active_session_ready: bool = False,
        active_session_has_messages: bool = False,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._messages = messages
        self._history_loading = False
        self._state = state
        self._active_session_ready = active_session_ready
        self._active_session_has_messages = active_session_has_messages

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

    @Property(str, constant=True)
    def state(self) -> str:
        return self._state

    @Property(str, constant=True)
    def lastError(self) -> str:
        return ""

    @Property(str, constant=True)
    def gatewayDetail(self) -> str:
        return ""

    @Property(bool, constant=True)
    def gatewayDetailIsError(self) -> bool:
        return False

    @Property(list, constant=True)
    def gatewayChannels(self) -> list[dict[str, object]]:
        return []

    @Property(bool, notify=activeSessionStateChanged)
    def activeSessionReady(self) -> bool:
        return self._active_session_ready

    @Property(bool, notify=activeSessionStateChanged)
    def activeSessionHasMessages(self) -> bool:
        return self._active_session_has_messages

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


class DummyConfigService(QObject):
    configLoaded = Signal()
    saveDone = Signal()
    saveError = Signal(str)
    stateChanged = Signal()

    def __init__(
        self,
        *,
        is_valid: bool = True,
        needs_setup: bool = False,
        language: str = "en",
        model: str | None = None,
        providers: list[dict[str, object]] | None = None,
        channels: dict[str, object] | None = None,
        config_file_path: str = "/tmp/.bao/config.jsonc",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._is_valid = is_valid
        self._needs_setup = needs_setup
        self._language = language
        self._ui_update: dict[str, object] = {}
        self._providers: list[dict[str, object]] = [dict(item) for item in (providers or [])]
        plain_channels = self._to_plain(channels or {})
        self._channels: dict[str, object] = (
            plain_channels if isinstance(plain_channels, dict) else {}
        )
        self._agents_defaults: dict[str, object] = {}
        self._config_file_path = config_file_path
        self.opened_config_directory = False
        if model is not None:
            self._agents_defaults["model"] = model
        self.last_saved_changes: object | None = None

    def _to_plain(self, value: object) -> object:
        to_variant = getattr(value, "toVariant", None)
        if callable(to_variant):
            return self._to_plain(to_variant())
        if isinstance(value, dict):
            return {str(k): self._to_plain(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._to_plain(item) for item in value]
        return value

    def _deep_merge(self, target: dict[str, object], patch: dict[str, object]) -> None:
        for key, value in patch.items():
            existing = target.get(key)
            if isinstance(value, dict) and isinstance(existing, dict):
                self._deep_merge(existing, value)
            else:
                target[key] = self._to_plain(value)

    @Property(bool, constant=True)
    def isValid(self) -> bool:
        return self._is_valid

    @Property(bool, constant=True)
    def needsSetup(self) -> bool:
        return self._needs_setup

    @Slot(str, result="QVariant")
    def getValue(self, path: str) -> object | None:
        data = {
            "ui": {"language": self._language, "update": dict(self._ui_update)},
            "channels": self._to_plain(self._channels),
            "providers": {
                provider.get("name", f"provider{index + 1}"): {
                    key: value for key, value in provider.items() if key != "name"
                }
                for index, provider in enumerate(self._providers)
                if isinstance(provider, dict)
            },
            "agents": {"defaults": dict(self._agents_defaults)},
        }
        node: object = data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node

    @Slot(result="QVariant")
    def getProviders(self) -> list[object]:
        return [dict(item) for item in self._providers]

    @Slot("QVariant", result=bool)
    def save(self, changes: object) -> bool:
        changes = self._to_plain(changes)
        self.last_saved_changes = changes
        if isinstance(changes, dict):
            ui = changes.get("ui")
            if isinstance(ui, dict):
                if isinstance(ui.get("language"), str):
                    self._language = ui["language"]
                update = ui.get("update")
                if isinstance(update, dict):
                    self._ui_update.update(update)

            providers = changes.get("providers")
            if isinstance(providers, dict):
                next_providers: list[dict[str, object]] = []
                for name, provider in providers.items():
                    if not isinstance(provider, dict):
                        continue
                    next_providers.append({"name": name, **provider})
                self._providers = next_providers

            channels = changes.get("channels")
            if isinstance(channels, dict):
                self._deep_merge(self._channels, channels)

            agents = changes.get("agents")
            if isinstance(agents, dict):
                defaults = agents.get("defaults")
                if isinstance(defaults, dict):
                    self._agents_defaults.update(defaults)

        self.saveDone.emit()
        self.configLoaded.emit()
        self.stateChanged.emit()
        return True

    @Slot(str, result=bool)
    def removeProvider(self, name: str) -> bool:
        _ = name
        return True

    @Slot(result=str)
    def getConfigFilePath(self) -> str:
        return self._config_file_path

    @Slot()
    def openConfigDirectory(self) -> None:
        self.opened_config_directory = True


class DummyDesktopPreferences(QObject):
    uiLanguageChanged = Signal()
    effectiveLanguageChanged = Signal()
    themeModeChanged = Signal()
    isDarkChanged = Signal()

    def __init__(
        self,
        *,
        ui_language: str = "en",
        theme_mode: str = "light",
        is_dark: bool = False,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._ui_language = ui_language
        self._theme_mode = theme_mode
        self._is_dark = is_dark

    @Property(str, notify=uiLanguageChanged)
    def uiLanguage(self) -> str:
        return self._ui_language

    @Property(str, notify=effectiveLanguageChanged)
    def effectiveLanguage(self) -> str:
        return self._ui_language

    @Property(str, notify=themeModeChanged)
    def themeMode(self) -> str:
        return self._theme_mode

    @Property(bool, notify=isDarkChanged)
    def isDark(self) -> bool:
        return self._is_dark

    @Slot(str, result=bool)
    def setUiLanguage(self, value: str) -> bool:
        self._ui_language = value
        self.uiLanguageChanged.emit()
        self.effectiveLanguageChanged.emit()
        return True

    @Slot(str, result=bool)
    def setThemeMode(self, value: str) -> bool:
        self._theme_mode = value
        self._is_dark = value == "dark"
        self.themeModeChanged.emit()
        self.isDarkChanged.emit()
        return True

    @Slot()
    def toggleTheme(self) -> None:
        _ = self.setThemeMode("light" if self._is_dark else "dark")


class DummyDiagnosticsService(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._log_file_path = "/tmp/bao-desktop.log"
        self._recent_log_text = "2026-03-08 03:19:15.301 | INFO | boot"
        self._events: list[dict[str, object]] = [
            {
                "code": "provider_error",
                "stage": "chat",
                "message": "provider timeout",
                "source": "provider",
                "timestamp": "2026-03-08T03:19:15",
                "session_key": "desktop:local",
                "level": "error",
            }
        ]
        self._observability_items: list[dict[str, object]] = [
            {"label": "Tool calls", "value": "5"},
            {"label": "Tool errors", "value": "1"},
        ]

    @Property(str, notify=changed)
    def logFilePath(self) -> str:
        return self._log_file_path

    @Property(str, notify=changed)
    def recentLogText(self) -> str:
        return self._recent_log_text

    @Property(list, notify=changed)
    def events(self) -> list[dict[str, object]]:
        return self._events

    @Property(list, notify=changed)
    def observabilityItems(self) -> list[dict[str, object]]:
        return self._observability_items

    @Property(int, notify=changed)
    def eventCount(self) -> int:
        return len(self._events)

    @Slot()
    def refresh(self) -> None:
        self.changed.emit()

    @Slot()
    def openLogDirectory(self) -> None:
        return None

    @Slot(result=str)
    def buildAssistantPrompt(self) -> str:
        return "Diagnostics prompt"


class DummySessionService(QObject):
    sessionsChanged = Signal()
    sidebarProjectionWillChange = Signal()
    sidebarProjectionChanged = Signal()
    activeKeyChanged = Signal(str)
    deleteCompleted = Signal(str, bool, str)
    activeReady = Signal()
    sessionsLoadingChanged = Signal(bool)

    def __init__(self, sessions_model: QAbstractListModel, parent: QObject | None = None) -> None:
        super().__init__(parent)
        from app.backend.session import SidebarRowsModel

        self._sessions_model = sessions_model
        self._sidebar_model = SidebarRowsModel()
        self._active_key = ""
        self._sessions_loading = False
        self._sidebar_expanded_groups: dict[str, bool] = {}
        self._sidebar_unread_count = 0
        self._sidebar_unread_fingerprint = ""
        self.new_session_calls: list[str] = []
        self.select_session_calls: list[str] = []
        self.delete_session_calls: list[str] = []
        self.sessionsChanged.connect(self._rebuild_sidebar_model)
        self._rebuild_sidebar_model()

    @Property(str, notify=activeKeyChanged)
    def activeKey(self) -> str:
        return self._active_key

    def setActiveKey(self, key: str) -> None:
        if self._active_key == key:
            return
        self._active_key = key
        rows = getattr(self._sessions_model, "_rows", None)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("key") == key:
                    row["has_unread"] = False
        self._ensure_group_expanded_for(key)
        self._rebuild_sidebar_model()
        self.activeKeyChanged.emit(key)

    @Property(QObject, constant=True)
    def sessionsModel(self) -> QObject:
        return self._sessions_model

    @Property(QObject, constant=True)
    def sidebarModel(self) -> QObject:
        return self._sidebar_model

    @Property(int, notify=sidebarProjectionChanged)
    def sidebarUnreadCount(self) -> int:
        return self._sidebar_unread_count

    @Property(str, notify=sidebarProjectionChanged)
    def sidebarUnreadFingerprint(self) -> str:
        return self._sidebar_unread_fingerprint

    @Property(bool, notify=sessionsLoadingChanged)
    def sessionsLoading(self) -> bool:
        return self._sessions_loading

    def setSessionsLoading(self, loading: bool) -> None:
        if self._sessions_loading == loading:
            return
        self._sessions_loading = loading
        self.sessionsLoadingChanged.emit(loading)

    @Slot(str)
    def newSession(self, name: str) -> None:
        self.new_session_calls.append(name)

    @Slot(str)
    def selectSession(self, key: str) -> None:
        self.select_session_calls.append(key)

    @Slot(str)
    def deleteSession(self, key: str) -> None:
        self.delete_session_calls.append(key)

    @Slot(str)
    def toggleSidebarGroup(self, channel: str) -> None:
        if not channel:
            return
        self._sidebar_expanded_groups[channel] = (
            self._sidebar_expanded_groups.get(channel, False) is not True
        )
        self._rebuild_sidebar_model()

    def _session_rows(self) -> list[dict[str, object]]:
        rows = getattr(self._sessions_model, "_rows", None)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, dict)]
        result: list[dict[str, object]] = []
        for i in range(self._sessions_model.rowCount()):
            idx = self._sessions_model.index(i)
            key = self._sessions_model.data(idx, int(Qt.ItemDataRole.UserRole) + 1)
            if not isinstance(key, str) or not key:
                continue
            result.append(
                {
                    "key": key,
                    "title": self._sessions_model.data(idx, int(Qt.ItemDataRole.UserRole) + 2)
                    or key,
                    "updated_label": self._sessions_model.data(
                        idx, int(Qt.ItemDataRole.UserRole) + 7
                    )
                    or "",
                    "channel": self._sessions_model.data(idx, int(Qt.ItemDataRole.UserRole) + 5)
                    or "other",
                    "has_unread": bool(
                        self._sessions_model.data(idx, int(Qt.ItemDataRole.UserRole) + 6) or False
                    ),
                    "session_kind": self._sessions_model.data(
                        idx, int(Qt.ItemDataRole.UserRole) + 10
                    )
                    or "regular",
                    "is_read_only": bool(
                        self._sessions_model.data(idx, int(Qt.ItemDataRole.UserRole) + 11) or False
                    ),
                    "parent_session_key": self._sessions_model.data(
                        idx, int(Qt.ItemDataRole.UserRole) + 12
                    )
                    or "",
                    "is_running": bool(
                        self._sessions_model.data(idx, int(Qt.ItemDataRole.UserRole) + 15) or False
                    ),
                }
            )
        return result

    def _initial_group_expanded(self, channel: str, items: list[dict[str, object]]) -> bool:
        if self._active_key and any(str(item.get("key", "")) == self._active_key for item in items):
            return True
        if self._active_key:
            return False
        return channel == "desktop"

    def _ensure_group_expanded_for(self, key: str) -> None:
        if not key:
            return
        for row in self._session_rows():
            if str(row.get("key", "")) != key:
                continue
            channel = str(row.get("channel", "") or "")
            if channel:
                self._sidebar_expanded_groups[channel] = True
            return

    def _rebuild_sidebar_model(self) -> None:
        self.sidebarProjectionWillChange.emit()
        sessions = self._session_rows()
        groups: dict[str, list[dict[str, object]]] = {}
        order: list[str] = []
        unread_parts: list[str] = []

        for session in sessions:
            channel = str(session.get("channel", "other") or "other")
            if channel not in groups:
                groups[channel] = []
                order.append(channel)
            session_copy = dict(session)
            if str(session_copy.get("key", "")) == self._active_key:
                session_copy["has_unread"] = False
            groups[channel].append(session_copy)
            if bool(session_copy.get("has_unread", False)):
                unread_parts.append(str(session_copy.get("key", "")))

        available = set(order)
        self._sidebar_expanded_groups = {
            channel: expanded
            for channel, expanded in self._sidebar_expanded_groups.items()
            if channel in available
        }
        order.sort(
            key=lambda channel: (
                (0, channel)
                if channel == "desktop"
                else ((2, channel) if channel == "heartbeat" else (1, channel))
            )
        )
        for channel in order:
            if channel in self._sidebar_expanded_groups:
                continue
            self._sidebar_expanded_groups[channel] = self._initial_group_expanded(
                channel, groups[channel]
            )

        rows: list[dict[str, object]] = []
        for channel in order:
            items = groups[channel]
            expanded = self._sidebar_expanded_groups.get(channel, False) is True
            child_buckets: dict[str, list[dict[str, object]]] = {}
            child_remainder: list[dict[str, object]] = []
            reordered_items: list[dict[str, object]] = []
            for item in items:
                if bool(item.get("session_kind") == "subagent_child") and str(
                    item.get("parent_session_key", "")
                ):
                    child_buckets.setdefault(str(item.get("parent_session_key", "")), []).append(
                        item
                    )
                elif item.get("session_kind") == "subagent_child":
                    child_remainder.append(item)
            for item in items:
                if item.get("session_kind") == "subagent_child":
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
            if not expanded:
                continue
            for index, item in enumerate(reordered_items):
                rows.append(
                    {
                        "row_id": f"session:{item.get('key', '')}",
                        "is_header": False,
                        "channel": channel,
                        "expanded": False,
                        "item_key": str(item.get("key", "")),
                        "item_title": str(item.get("title", item.get("key", "")) or ""),
                        "item_updated_text": str(item.get("updated_label", "") or ""),
                        "visual_channel": "subagent"
                        if item.get("session_kind") == "subagent_child"
                        else str(item.get("channel", channel) or channel),
                        "is_read_only": bool(item.get("is_read_only", False)),
                        "is_running": bool(item.get("is_running", False)),
                        "is_child_session": item.get("session_kind") == "subagent_child",
                        "parent_session_key": str(item.get("parent_session_key", "") or ""),
                        "item_has_unread": bool(item.get("has_unread", False)),
                        "item_count": 0,
                        "group_unread_count": 0,
                        "group_has_running": False,
                        "is_last_in_group": index == len(reordered_items) - 1,
                        "is_first_in_group": index == 0,
                    }
                )

        active_index = self._sidebar_model.active_row_index(self._active_key)
        if active_index >= 0 and self._active_key:
            next_index = next(
                (
                    idx
                    for idx, row in enumerate(rows)
                    if str(row.get("item_key", "")) == self._active_key
                ),
                -1,
            )
            if next_index >= 0 and next_index != active_index:
                pinned = rows.pop(next_index)
                rows.insert(max(0, min(active_index, len(rows))), pinned)

        unread_parts.sort()
        self._sidebar_model.sync_rows(rows)
        self._sidebar_unread_count = len(unread_parts)
        self._sidebar_unread_fingerprint = "|".join(unread_parts)
        self.sidebarProjectionChanged.emit()


class DummyUpdateService(QObject):
    quitRequested = Signal()

    @Property(str, constant=True)
    def state(self) -> str:
        return "idle"

    @Property(str, constant=True)
    def currentVersion(self) -> str:
        return "0.0.0"

    @Property(str, constant=True)
    def latestVersion(self) -> str:
        return ""

    @Property(str, constant=True)
    def notesMarkdown(self) -> str:
        return ""

    @Property(str, constant=True)
    def errorMessage(self) -> str:
        return ""

    @Property(float, constant=True)
    def downloadProgress(self) -> float:
        return 0.0

    @Slot()
    def reloadConfig(self) -> None:
        return None

    @Slot()
    def checkForUpdates(self) -> None:
        return None

    @Slot()
    def installUpdate(self) -> None:
        return None


class DummyUpdateBridge(QObject):
    @Slot()
    def reloadRequested(self) -> None:
        return None

    @Slot()
    def checkRequested(self) -> None:
        return None

    @Slot()
    def installRequested(self) -> None:
        return None


@pytest.fixture(scope="session")
def qapp():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    yield app


def _process(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _install_focus_filter(root: QObject) -> WindowFocusDismissFilter:
    focus_filter = WindowFocusDismissFilter(root)
    app = QGuiApplication.instance()
    if app is not None:
        app.installEventFilter(focus_filter)
    if hasattr(root, "installEventFilter"):
        root.installEventFilter(focus_filter)
    return focus_filter


def _remove_focus_filter(root: QObject, focus_filter: WindowFocusDismissFilter | None) -> None:
    if focus_filter is None:
        return
    app = QGuiApplication.instance()
    if app is not None:
        app.removeEventFilter(focus_filter)
    if hasattr(root, "removeEventFilter"):
        root.removeEventFilter(focus_filter)


def _find_chat_input(root: QObject) -> QObject:
    for obj in root.findChildren(QObject):
        if obj.objectName() == "chatMessageInput":
            return obj
    raise AssertionError("chat composer TextArea not found")


def _find_toast(root: QObject) -> QObject:
    for obj in root.findChildren(QObject):
        try:
            if obj.objectName() == "globalToast":
                return obj
        except Exception:
            continue
    raise AssertionError("global toast not found")


def _load_main_window(
    config_service: DummyConfigService | None = None,
    messages_model: QAbstractListModel | None = None,
    session_model: QAbstractListModel | None = None,
    chat_service: DummyChatService | None = None,
    diagnostics_service: QObject | None = None,
    desktop_preferences: DummyDesktopPreferences | None = None,
) -> tuple[QQmlApplicationEngine, QObject]:
    messages_model = messages_model or EmptyMessagesModel()
    chat_service = chat_service or DummyChatService(messages_model)
    config_service = config_service or DummyConfigService()
    session_service = DummySessionService(session_model or messages_model)
    update_service = DummyUpdateService()
    update_bridge = DummyUpdateBridge()
    diagnostics_service = diagnostics_service or QObject()
    desktop_preferences = desktop_preferences or DummyDesktopPreferences()
    engine = QQmlApplicationEngine()
    engine._test_refs = {
        "messages_model": messages_model,
        "chat_service": chat_service,
        "config_service": config_service,
        "session_service": session_service,
        "update_service": update_service,
        "update_bridge": update_bridge,
        "diagnostics_service": diagnostics_service,
        "desktop_preferences": desktop_preferences,
    }
    context = engine.rootContext()
    context.setContextProperty("chatService", chat_service)
    context.setContextProperty("configService", config_service)
    context.setContextProperty("sessionService", session_service)
    context.setContextProperty("updateService", update_service)
    context.setContextProperty("updateBridge", update_bridge)
    context.setContextProperty("diagnosticsService", diagnostics_service)
    context.setContextProperty("desktopPreferences", desktop_preferences)
    context.setContextProperty("messagesModel", messages_model)
    context.setContextProperty("systemUiLanguage", "en")
    engine.load(QUrl.fromLocalFile(str(MAIN_QML_PATH)))
    root_objects = engine.rootObjects()
    assert root_objects
    root = root_objects[0]
    if hasattr(root, "requestActivate"):
        root.requestActivate()
    for _ in range(5):
        _process(30)
    return engine, root


def _load_light_main_window(
    config_service: DummyConfigService | None = None,
    messages_model: QAbstractListModel | None = None,
    session_model: QAbstractListModel | None = None,
    chat_service: DummyChatService | None = None,
    diagnostics_service: QObject | None = None,
) -> tuple[QQmlApplicationEngine, QObject]:
    return _load_main_window(
        config_service=config_service,
        messages_model=messages_model,
        session_model=session_model,
        chat_service=chat_service,
        diagnostics_service=diagnostics_service,
        desktop_preferences=DummyDesktopPreferences(theme_mode="light", is_dark=False),
    )


def _load_inline_qml(
    source: str, *, config_service: QObject | None = None
) -> tuple[QQmlApplicationEngine, QObject]:
    engine = QQmlApplicationEngine()
    context = engine.rootContext()
    context.setContextProperty("configService", config_service or DummyConfigService())
    context.setContextProperty("sizeDropdownMaxHeight", 280)
    context.setContextProperty("spacingSm", 8)
    context.setContextProperty("textSecondary", "#666666")
    context.setContextProperty("textTertiary", "#888888")
    context.setContextProperty("textPrimary", "#111111")
    context.setContextProperty("typeLabel", 14)
    context.setContextProperty("typeCaption", 12)
    context.setContextProperty("typeButton", 14)
    context.setContextProperty("weightMedium", 500)
    context.setContextProperty("letterTight", 0)
    context.setContextProperty("sizeControlHeight", 40)
    context.setContextProperty("radiusSm", 10)
    context.setContextProperty("bgInputFocus", "#FFFFFF")
    context.setContextProperty("bgInputHover", "#F7F7F7")
    context.setContextProperty("bgInput", "#F2F2F2")
    context.setContextProperty("borderFocus", "#FFB33D")
    context.setContextProperty("borderSubtle", "#DDDDDD")
    context.setContextProperty("motionUi", 220)
    context.setContextProperty("motionFast", 180)
    context.setContextProperty("motionMicro", 120)
    context.setContextProperty("easeStandard", QtCore.QEasingCurve.Type.OutCubic)
    context.setContextProperty("sizeFieldPaddingX", 12)
    context.setContextProperty("isDark", False)
    context.setContextProperty("sizeOptionHeight", 36)
    component = QtQml.QQmlComponent(engine)
    component.setData(
        source.encode("utf-8"),
        QUrl.fromLocalFile(str(PROJECT_ROOT / "tests" / "inline_settings_select.qml")),
    )
    root = component.create()
    if root is None:
        errors = "\n".join(err.toString() for err in component.errors())
        raise AssertionError(errors)
    engine._inline_refs = {"component": component, "root": root}
    return engine, root


def _find_object(root: QObject, object_name: str) -> QObject:
    for obj in root.findChildren(QObject):
        if obj.objectName() == object_name:
            return obj
    raise AssertionError(f"object not found: {object_name}")


def _first_visible_sidebar_session_anchor(
    root: QObject, session_list: QObject
) -> tuple[str, float]:
    _ = root
    content_y = float(session_list.property("contentY"))
    content_item = session_list.property("contentItem")
    if not isinstance(content_item, QQuickItem):
        raise AssertionError("sidebar content item not found")
    delegates = []
    for obj in content_item.childItems():
        if not bool(obj.property("anchorReady")):
            continue
        if bool(obj.property("anchorIsHeader")):
            continue
        key = str(obj.property("anchorKey") or "")
        if not key:
            continue
        y = float(obj.property("y"))
        height = float(obj.property("height"))
        if height <= 0:
            continue
        if y + height <= content_y:
            continue
        delegates.append((y, key))
    if not delegates:
        raise AssertionError("visible sidebar session anchor not found")
    delegates.sort(key=lambda item: item[0])
    y, key = delegates[0]
    return key, content_y - y


def _sidebar_session_anchor_offset(session_list: QObject, key: str) -> float:
    content_y = float(session_list.property("contentY"))
    content_item = session_list.property("contentItem")
    if not isinstance(content_item, QQuickItem):
        raise AssertionError("sidebar content item not found")
    for obj in content_item.childItems():
        if not bool(obj.property("anchorReady")):
            continue
        if bool(obj.property("anchorIsHeader")):
            continue
        if str(obj.property("anchorKey") or "") != key:
            continue
        y = float(obj.property("y"))
        height = float(obj.property("height"))
        if height <= 0:
            continue
        if y + height <= content_y:
            continue
        if y >= content_y + float(session_list.property("height")):
            continue
        return content_y - y
    raise AssertionError(f"sidebar anchor not visible: {key}")


def _sidebar_delegate_y(session_list: QObject, key: str) -> float:
    content_item = session_list.property("contentItem")
    if not isinstance(content_item, QQuickItem):
        raise AssertionError("sidebar content item not found")
    for obj in content_item.childItems():
        if not bool(obj.property("anchorReady")):
            continue
        if bool(obj.property("anchorIsHeader")):
            continue
        if str(obj.property("anchorKey") or "") != key:
            continue
        return float(obj.property("y"))
    raise AssertionError(f"sidebar delegate not found: {key}")


def _sidebar_delegate_root(session_list: QObject, key: str) -> QQuickItem:
    content_item = session_list.property("contentItem")
    if not isinstance(content_item, QQuickItem):
        raise AssertionError("sidebar content item not found")
    for obj in content_item.childItems():
        if not bool(obj.property("anchorReady")):
            continue
        if bool(obj.property("anchorIsHeader")):
            continue
        if str(obj.property("anchorKey") or "") != key:
            continue
        return obj
    raise AssertionError(f"sidebar delegate root not found: {key}")


def _find_object_by_property(root: QObject, property_name: str, expected: object) -> QObject:
    for obj in root.findChildren(QObject):
        try:
            if obj.property(property_name) == expected:
                return obj
        except Exception:
            continue
    raise AssertionError(f"object with {property_name}={expected!r} not found")


def _find_visible_object_by_property(
    root: QObject, property_name: str, expected: object
) -> QObject:
    for obj in root.findChildren(QObject):
        try:
            if obj.property(property_name) != expected:
                continue
            if obj.property("visible") is not True:
                continue
            return obj
        except Exception:
            continue
    raise AssertionError(f"visible object with {property_name}={expected!r} not found")


def _center_point(item: QObject) -> QPoint:
    center = item.mapToScene(QPointF(item.property("width") / 2, item.property("height") / 2))
    return QPoint(int(center.x()), int(center.y()))


def _provider_list_snapshot(settings_view: QObject) -> list[dict[str, object]]:
    provider_list = settings_view.property("_providerList")
    to_variant = getattr(provider_list, "toVariant", None)
    if callable(to_variant):
        provider_list = to_variant()
    if not isinstance(provider_list, list):
        raise AssertionError("settings provider list is not a list")
    snapshot: list[dict[str, object]] = []
    for item in provider_list:
        if not isinstance(item, dict):
            raise AssertionError("settings provider row is not a dict")
        snapshot.append(item)
    return snapshot


def _scroll_item_into_view(root: QObject, scroll_view: QObject, item: QObject) -> None:
    content_item = scroll_view.property("contentItem")
    if not isinstance(content_item, QQuickItem):
        raise AssertionError("settings scroll content item not found")
    scene_center = item.mapToScene(QPointF(item.property("width") / 2, item.property("height") / 2))
    window_height = float(root.property("height"))
    current_y = float(content_item.property("contentY"))
    lower_bound = window_height - 120
    upper_bound = 120.0
    if scene_center.y() > lower_bound:
        content_item.setProperty("contentY", current_y + (scene_center.y() - lower_bound))
        _process(50)
    elif scene_center.y() < upper_bound:
        content_item.setProperty("contentY", max(0.0, current_y - (upper_bound - scene_center.y())))
        _process(50)


def test_main_chat_view_composer_click_focus_works_with_window_focus_filter(qapp):
    _ = qapp
    engine, root = _load_main_window()
    focus_filter: WindowFocusDismissFilter | None = None

    try:
        focus_filter = _install_focus_filter(root)
        message_input = _find_chat_input(root)

        message_input.forceActiveFocus()
        _process(0)
        assert bool(message_input.property("activeFocus")) is True

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(message_input))
        _process(0)

        assert bool(message_input.property("activeFocus")) is True
    finally:
        _remove_focus_filter(root, focus_filter)
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_diagnostics_modal_renders_content(qapp):
    _ = qapp
    engine, root = _load_main_window(
        chat_service=DummyChatService(EmptyMessagesModel(), state="running"),
        diagnostics_service=DummyDiagnosticsService(),
    )

    try:
        modal = _find_object(root, "diagnosticsModal")
        _ = QMetaObject.invokeMethod(modal, "open")
        _process(150)

        _find_object_by_property(root, "text", "Gateway State")
        _find_object_by_property(root, "text", "Running normally")
        _find_object_by_property(root, "text", "Log file")
        _find_object_by_property(root, "text", "/tmp/bao-desktop.log")
        _find_object_by_property(root, "text", "Log tail")

        gateway_card = _find_object(root, "diagnosticsGatewayCard")
        log_file_card = _find_object(root, "diagnosticsLogFileCard")
        events_card = _find_object(root, "diagnosticsEventsCard")
        log_tail_card = _find_object(root, "diagnosticsLogTailCard")

        assert int(gateway_card.property("width")) > 260
        assert int(log_file_card.property("width")) > 260
        assert int(events_card.property("width")) > 260
        assert int(log_tail_card.property("width")) > 260
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_external_click_clears_selection_with_window_focus_filter(qapp):
    _ = qapp
    engine, root = _load_main_window()
    focus_filter: WindowFocusDismissFilter | None = None

    try:
        focus_filter = _install_focus_filter(root)
        message_input = _find_chat_input(root)

        _ = message_input.setProperty("text", "hello bao")
        message_input.forceActiveFocus()
        _process(0)
        message_input.select(0, 5)
        _process(0)

        assert bool(message_input.property("activeFocus")) is True
        assert str(message_input.property("selectedText")) == "hello"

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, QPoint(20, 120))
        _process(0)

        assert bool(message_input.property("activeFocus")) is False
        assert str(message_input.property("selectedText")) == ""
    finally:
        _remove_focus_filter(root, focus_filter)
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_setup_mode_hides_sidebar_and_lands_on_settings(qapp):
    _ = qapp
    engine, root = _load_main_window(DummyConfigService(is_valid=False, needs_setup=True))

    try:
        sidebar = _find_object(root, "appSidebar")
        stack = _find_object(root, "mainStack")

        assert bool(root.property("setupMode")) is True
        assert bool(sidebar.property("visible")) is False
        assert int(stack.property("currentIndex")) == 1
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_settings_advanced_section_shows_config_folder_entry(qapp):
    _ = qapp
    config_service = DummyConfigService(config_file_path="/tmp/.bao/config.jsonc")
    engine, root = _load_main_window(config_service)

    try:
        settings_view = _find_object(root, "settingsView")
        _ = root.setProperty("startView", "settings")
        _ = settings_view.setProperty("_activeTab", 2)
        _process(30)

        open_button = _find_visible_object_by_property(root, "text", "Open Config Folder")
        _find_object_by_property(root, "text", "/tmp/.bao/config.jsonc")

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(open_button))
        _process(0)

        assert config_service.opened_config_directory is True
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_onboarding_invalid_ui_language_stays_on_first_step(qapp):
    _ = qapp
    config_service = DummyConfigService(is_valid=False, needs_setup=True, language="fr")
    engine, root = _load_main_window(
        config_service,
        desktop_preferences=DummyDesktopPreferences(ui_language="fr"),
    )

    try:
        settings_view = _find_object(root, "settingsView")

        assert bool(root.property("setupMode")) is True
        assert settings_view.property("onboardingUiLanguage") == "auto"
        assert bool(settings_view.property("languageConfigured")) is False
        assert int(settings_view.property("onboardingStepIndex")) == 0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_onboarding_custom_model_preset_clears_previous_recommended_value(qapp):
    _ = qapp
    config_service = DummyConfigService(
        is_valid=False,
        needs_setup=True,
        model="openai/gpt-4o",
    )
    engine, root = _load_main_window(config_service)

    try:
        settings_view = _find_object(root, "settingsView")
        _ = settings_view.setProperty(
            "_providerList",
            [{"name": "primary", "type": "openai", "apiKey": "sk-ok", "apiBase": ""}],
        )
        _process(30)

        assert settings_view.property("onboardingDraftModel") == "openai/gpt-4o"
        assert QMetaObject.invokeMethod(settings_view, "activateCustomModelInput")
        assert settings_view.property("onboardingDraftModel") == ""
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


@pytest.mark.parametrize(
    ("provider_row", "expected_name", "expected_type", "expected_api_base"),
    [
        (
            {"name": "anthropic", "type": "anthropic", "apiKey": "sk-old", "apiBase": ""},
            "anthropic",
            "anthropic",
            "",
        ),
        (
            {
                "name": "openrouter",
                "type": "openai",
                "apiKey": "sk-old",
                "apiBase": "https://openrouter.ai/api/v1",
            },
            "openrouter",
            "openai",
            "https://openrouter.ai/api/v1",
        ),
    ],
)
def test_onboarding_provider_save_stays_in_sync(
    qapp,
    provider_row: dict[str, object],
    expected_name: str,
    expected_type: str,
    expected_api_base: str,
):
    _ = qapp
    config_service = DummyConfigService(
        is_valid=False,
        needs_setup=True,
        providers=[{"name": "primary", "type": "openai", "apiKey": "sk-old", "apiBase": ""}],
    )
    engine, root = _load_main_window(config_service)

    try:
        settings_view = _find_object(root, "settingsView")

        _ = settings_view.setProperty("_providerList", [provider_row])
        _process(30)

        assert QMetaObject.invokeMethod(settings_view, "saveOnboardingProviderStep")

        assert isinstance(config_service.last_saved_changes, dict)
        providers = config_service.last_saved_changes.get("providers")
        assert isinstance(providers, dict)
        assert providers[expected_name]["type"] == expected_type
        assert providers[expected_name]["apiKey"] == "sk-old"
        assert providers[expected_name]["apiBase"] == expected_api_base
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_settings_select_missing_value_does_not_emit_default_current_value(qapp):
    _ = qapp
    qml_import = (PROJECT_ROOT / "app" / "qml").as_uri()
    engine, root = _load_inline_qml(
        f'''
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "{qml_import}"

Item {{
    width: 320
    height: 120

    SettingsSelect {{
        id: select
        objectName: "settingsSelect"
        label: "Context"
        dotpath: "agents.defaults.contextManagement"
        options: [
            {{"label": "off", "value": "off"}},
            {{"label": "auto", "value": "auto"}}
        ]
    }}
}}
'''
    )

    try:
        select = _find_object(root, "settingsSelect")
        _process(0)
        assert select.property("currentValue") is None
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_channel_row_toggle_click_updates_checked_state(qapp):
    _ = qapp
    engine, root = _load_main_window()

    try:
        settings_view = _find_object(root, "settingsView")
        _ = root.setProperty("startView", "settings")
        _ = settings_view.setProperty("_activeTab", 1)
        _process(30)

        toggle = _find_object_by_property(root, "dotpath", "channels.telegram.enabled")
        assert toggle.property("checked") is False
        assert toggle.property("currentValue") is None

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(toggle))
        _process(0)

        assert toggle.property("checked") is True
        assert toggle.property("currentValue") is True
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_channel_section_save_ignores_untouched_disabled_toggle(qapp):
    _ = qapp
    config_service = DummyConfigService(channels={"telegram": {"token": "123456:ABC"}})
    engine, root = _load_main_window(config_service)

    try:
        settings_view = _find_object(root, "settingsView")
        _ = root.setProperty("startView", "settings")
        _ = settings_view.setProperty("_activeTab", 1)
        _process(30)

        save_button = _find_visible_object_by_property(root, "text", "Save")
        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(save_button))
        _process(30)

        assert isinstance(config_service.last_saved_changes, dict)
        assert "channels.telegram.enabled" not in config_service.last_saved_changes
        assert config_service.last_saved_changes.get("channels.telegram.token") == "123456:ABC"
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_channel_section_save_persists_touched_toggle(qapp):
    _ = qapp
    config_service = DummyConfigService(channels={"telegram": {"token": "123456:ABC"}})
    engine, root = _load_main_window(config_service)

    try:
        settings_view = _find_object(root, "settingsView")
        _ = root.setProperty("startView", "settings")
        _ = settings_view.setProperty("_activeTab", 1)
        _process(30)

        toggle = _find_object_by_property(root, "dotpath", "channels.telegram.enabled")
        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(toggle))
        _process(0)

        save_button = _find_visible_object_by_property(root, "text", "Save")
        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(save_button))
        _process(30)

        assert isinstance(config_service.last_saved_changes, dict)
        assert config_service.last_saved_changes.get("channels.telegram.enabled") is True
        assert config_service.last_saved_changes.get("channels.telegram.token") == "123456:ABC"
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_add_new_provider_expands_new_card(qapp):
    _ = qapp
    engine, root = _load_main_window()

    try:
        _ = root.setProperty("startView", "settings")
        settings_view = _find_object(root, "settingsView")
        _process(30)

        assert QMetaObject.invokeMethod(settings_view, "_addNewProvider")
        for _ in range(8):
            _process(30)
            provider_list = _provider_list_snapshot(settings_view)
            if isinstance(provider_list, list) and len(provider_list) == 1:
                break

        provider_list = _provider_list_snapshot(settings_view)
        assert len(provider_list) == 1
        assert provider_list[0]["name"] == "primary"
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_settings_add_provider_click_works_with_focused_editor(qapp):
    _ = qapp
    config_service = DummyConfigService(
        model="openai/gpt-4o",
        providers=[{"name": "primary", "type": "openai", "apiKey": "sk-ready", "apiBase": ""}],
    )
    engine, root = _load_main_window(config_service)
    focus_filter: WindowFocusDismissFilter | None = None

    try:
        focus_filter = _install_focus_filter(root)
        _ = root.setProperty("startView", "settings")
        settings_view = _find_object(root, "settingsView")
        _process(30)

        workspace_field = _find_object_by_property(root, "placeholderText", "~/.bao/workspace")
        settings_scroll = _find_object(root, "settingsScroll")
        add_provider_button = _find_object(root, "addProviderHitArea")

        workspace_field.forceActiveFocus()
        _process(0)
        assert len(_provider_list_snapshot(settings_view)) == 1

        _scroll_item_into_view(root, settings_scroll, add_provider_button)

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(add_provider_button))
        _process(150)

        assert bool(workspace_field.property("activeFocus")) is False
        assert settings_view.property("_pendingExpandProviderName") == ""
        assert len(_provider_list_snapshot(settings_view)) == 2
    finally:
        _remove_focus_filter(root, focus_filter)
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_settings_save_click_works_with_open_settings_select_popup(qapp):
    _ = qapp
    config_service = DummyConfigService(
        model="openai/gpt-4o",
        providers=[{"name": "primary", "type": "openai", "apiKey": "sk-ready", "apiBase": ""}],
    )
    engine, root = _load_main_window(config_service)
    focus_filter: WindowFocusDismissFilter | None = None

    try:
        focus_filter = _install_focus_filter(root)
        _ = root.setProperty("startView", "settings")
        popup_owner = _find_visible_object_by_property(root, "baoClickAwayPopupOwner", True)
        save_button = _find_visible_object_by_property(root, "text", "Save")
        _process(30)

        popup_owner.openPopup()
        _process(100)

        assert bool(popup_owner.property("baoClickAwayPopupOpen")) is True

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(save_button))
        _process(100)

        assert isinstance(config_service.last_saved_changes, dict)
    finally:
        _remove_focus_filter(root, focus_filter)
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_settings_channel_header_click_works_with_focused_editor(qapp):
    _ = qapp
    config_service = DummyConfigService(
        model="openai/gpt-4o",
        providers=[{"name": "primary", "type": "openai", "apiKey": "sk-ready", "apiBase": ""}],
        channels={"telegram": {"enabled": True, "token": "123456:ABC"}},
    )
    engine, root = _load_main_window(config_service)
    focus_filter: WindowFocusDismissFilter | None = None

    try:
        focus_filter = _install_focus_filter(root)
        _ = root.setProperty("startView", "settings")
        settings_view = _find_object(root, "settingsView")
        _ = settings_view.setProperty("_activeTab", 1)
        _process(30)

        workspace_field = _find_object_by_property(root, "placeholderText", "~/.bao/workspace")
        channel_row = _find_object(root, "channelRow_telegram")
        channel_header = _find_object(root, "channelHeader_telegram")

        workspace_field.forceActiveFocus()
        _process(0)

        assert bool(workspace_field.property("activeFocus")) is True
        assert bool(channel_row.property("expanded")) is False

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(channel_header))
        _process(50)

        assert bool(channel_row.property("expanded")) is True
        assert bool(workspace_field.property("activeFocus")) is False

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(channel_header))
        _process(50)

        assert bool(channel_row.property("expanded")) is False
    finally:
        _remove_focus_filter(root, focus_filter)
        root.deleteLater()
        engine.deleteLater()
        _process(0)


@pytest.mark.parametrize("initial_enabled", [False, True])
def test_channel_section_save_preserves_existing_enabled_value(qapp, initial_enabled):
    _ = qapp
    config_service = DummyConfigService(
        channels={"telegram": {"enabled": initial_enabled, "token": "123456:ABC"}}
    )
    engine, root = _load_main_window(config_service)

    try:
        settings_view = _find_object(root, "settingsView")
        _ = root.setProperty("startView", "settings")
        _ = settings_view.setProperty("_activeTab", 1)
        _process(30)

        save_button = _find_visible_object_by_property(root, "text", "Save")
        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(save_button))
        _process(30)

        assert isinstance(config_service.last_saved_changes, dict)
        assert config_service.last_saved_changes.get("channels.telegram.enabled") is initial_enabled
        assert config_service.last_saved_changes.get("channels.telegram.token") == "123456:ABC"
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_onboarding_final_cta_requires_model_selection(qapp):
    _ = qapp
    config_service = DummyConfigService(
        is_valid=False,
        needs_setup=True,
        providers=[{"name": "primary", "type": "openai", "apiKey": "sk-ready", "apiBase": ""}],
    )
    engine, root = _load_main_window(config_service)

    try:
        settings_view = _find_object(root, "settingsView")
        model_section = _find_object_by_property(
            settings_view, "actionText", "Save and start chatting"
        )
        model_field = _find_object(root, "onboardingPrimaryModelField")

        _process(30)
        assert settings_view.property("providerConfigured") is True
        assert settings_view.property("onboardingModelReady") is False
        assert model_section.property("actionEnabled") is False

        model_field.setCurrentText("openai/gpt-4o")
        _process(30)

        assert settings_view.property("onboardingModelReady") is True
        assert model_section.property("actionEnabled") is True
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_empty_state_click_creates_new_session(qapp):
    _ = qapp
    engine, root = _load_main_window()

    try:
        session_service = engine._test_refs["session_service"]
        empty_state = _find_object(root, "sidebarEmptyState")

        assert bool(empty_state.property("visible")) is True

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(empty_state))
        _process(0)

        assert session_service.new_session_calls == [""]
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_loading_state_hides_empty_cta(qapp):
    _ = qapp
    engine, root = _load_main_window()

    try:
        session_service = engine._test_refs["session_service"]
        empty_state = _find_object(root, "sidebarEmptyState")
        loading_state = _find_object(root, "sidebarLoadingState")

        session_service.setSessionsLoading(True)
        _process(0)

        assert bool(loading_state.property("visible")) is True
        assert bool(empty_state.property("visible")) is False
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_new_session_button_click_creates_new_session(qapp):
    _ = qapp
    engine, root = _load_main_window()

    try:
        session_service = engine._test_refs["session_service"]
        button = _find_object(root, "newSessionButton")

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(button))
        _process(0)

        assert session_service.new_session_calls == [""]
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_empty_session_prefers_ready_state_over_gateway_idle_message(qapp):
    _ = qapp
    chat_service = DummyChatService(
        EmptyMessagesModel(),
        state="idle",
        active_session_ready=True,
        active_session_has_messages=False,
    )
    engine, root = _load_main_window(chat_service=chat_service)

    try:
        ready_state = _find_object(root, "chatEmptyReadyState")
        idle_state = _find_object(root, "chatEmptyIdleState")

        _process(20)

        assert bool(ready_state.property("visible")) is True
        assert bool(idle_state.property("visible")) is False
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_light_theme_setup_empty_icon_uses_light_asset(qapp):
    _ = qapp
    config_service = DummyConfigService(is_valid=False, needs_setup=True)
    engine, root = _load_light_main_window(config_service=config_service)

    try:
        icon = _find_object(root, "chatEmptySetupIcon")

        assert "settings-light.svg" in str(icon.property("source"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_light_theme_ready_empty_icon_uses_light_asset(qapp):
    _ = qapp
    chat_service = DummyChatService(
        EmptyMessagesModel(),
        state="running",
        active_session_ready=True,
        active_session_has_messages=False,
    )
    engine, root = _load_light_main_window(chat_service=chat_service)

    try:
        icon = _find_object(root, "chatEmptyReadyIcon")

        assert "chat-light.svg" in str(icon.property("source"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_light_theme_idle_empty_icons_use_light_assets(qapp):
    _ = qapp
    engine, root = _load_light_main_window()

    try:
        idle_icon = _find_object(root, "chatEmptyIdleIcon")
        sidebar_empty_icon = _find_object(root, "sidebarEmptyChatIcon")
        sidebar_title_icon = _find_object(root, "sidebarSessionsTitleIcon")

        assert "zap-light.svg" in str(idle_icon.property("source"))
        assert "chat-light.svg" in str(sidebar_empty_icon.property("source"))
        assert "sidebar-sessions-title-light.svg" in str(sidebar_title_icon.property("source"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_light_theme_main_greeting_tokens_use_light_values(qapp):
    _ = qapp
    engine, root = _load_light_main_window()

    try:
        assert "ignite-light.svg" in str(root.property("chatGreetingIconSource"))
        assert root.property("chatGreetingBubbleBgStart") == root.property(
            "chatGreetingBubbleBgEnd"
        )
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_session_selection_keeps_stack_bound_to_start_view(qapp):
    _ = qapp
    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    engine, root = _load_main_window(session_model=session_model)

    try:
        sidebar = _find_object(root, "appSidebar")
        stack = _find_object(root, "mainStack")
        session_service = engine._test_refs["session_service"]

        _ = root.setProperty("startView", "settings")
        _process(20)
        assert int(stack.property("currentIndex")) == 1

        sidebar.sessionSelected.emit("desktop:local::default")
        _process(20)

        assert session_service.select_session_calls == ["desktop:local::default"]
        assert root.property("startView") == "chat"
        assert int(stack.property("currentIndex")) == 0

        _ = root.setProperty("startView", "settings")
        _process(20)

        assert int(stack.property("currentIndex")) == 1
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_gateway_detail_bubble_shows_error_without_hover(qapp):
    _ = qapp

    class GatewayDetailChatService(DummyChatService):
        def __init__(self, messages: QAbstractListModel) -> None:
            super().__init__(messages)
            self._state_value = "running"
            self._last_error_value = "⚠ Channel start failed: telegram: bad token"
            self._gateway_detail_value = self._last_error_value

        @Property(str, constant=True)
        def state(self) -> str:
            return self._state_value

        @Property(str, constant=True)
        def lastError(self) -> str:
            return self._last_error_value

        @Property(str, constant=True)
        def gatewayDetail(self) -> str:
            return self._gateway_detail_value

        @Property(bool, constant=True)
        def gatewayDetailIsError(self) -> bool:
            return True

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    chat_service = GatewayDetailChatService(EmptyMessagesModel())
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        orb = _find_object(root, "gatewayDetailOrb")
        bubble = _find_object(root, "gatewayDetailBubble")
        text = _find_object(root, "gatewayDetailText")

        assert bool(orb.property("visible")) is True
        assert bool(bubble.property("visible")) is False

        QTest.mouseMove(root, QPoint(0, 0))
        _process(20)
        QTest.mouseMove(root, _center_point(orb))
        _process(40)

        assert bool(bubble.property("visible")) is True
        assert "telegram" in str(text.property("text"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_gateway_detail_bubble_shows_summary_on_hover(qapp):
    _ = qapp

    class GatewaySummaryChatService(DummyChatService):
        def __init__(self, messages: QAbstractListModel) -> None:
            super().__init__(messages)
            self._gateway_detail_value = "✓ Gateway started — channels: telegram"

        @Property(str, constant=True)
        def gatewayDetail(self) -> str:
            return self._gateway_detail_value

        @Property(bool, constant=True)
        def gatewayDetailIsError(self) -> bool:
            return False

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    chat_service = GatewaySummaryChatService(EmptyMessagesModel())
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        bubble = _find_object(root, "gatewayDetailBubble")
        text = _find_object(root, "gatewayDetailText")

        assert bool(bubble.property("visible")) is False

        QTest.mouseMove(root, QPoint(0, 0))
        _process(20)
        orb = _find_object(root, "gatewayDetailOrb")
        QTest.mouseMove(root, _center_point(orb))
        _process(40)
        if not bool(bubble.property("visible")):
            QTest.mouseMove(root, _center_point(orb))
            _process(40)

        assert bool(bubble.property("visible")) is True
        assert "Gateway started" in str(text.property("text"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_gateway_detail_bubble_stays_hidden_on_focus_without_hover(qapp):
    _ = qapp

    class GatewaySummaryChatService(DummyChatService):
        def __init__(self, messages: QAbstractListModel) -> None:
            super().__init__(messages)
            self._gateway_detail_value = "✓ Gateway started — channels: telegram"

        @Property(str, constant=True)
        def gatewayDetail(self) -> str:
            return self._gateway_detail_value

        @Property(bool, constant=True)
        def gatewayDetailIsError(self) -> bool:
            return False

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    chat_service = GatewaySummaryChatService(EmptyMessagesModel())
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        orb = _find_object(root, "gatewayDetailOrb")
        bubble = _find_object(root, "gatewayDetailBubble")
        capsule = _find_object(root, "gatewayCapsule")

        assert bool(bubble.property("visible")) is False
        assert bool(orb.property("visible")) is True
        capsule.forceActiveFocus()
        _process(20)

        assert bool(capsule.property("activeFocus")) is True
        assert bool(bubble.property("visible")) is False
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_gateway_capsule_is_keyboard_focusable(qapp):
    _ = qapp

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    chat_service = DummyChatService(EmptyMessagesModel())
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        capsule = _find_object(root, "gatewayCapsule")
        assert bool(capsule.property("activeFocusOnTab")) is True
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_gateway_capsule_space_key_triggers_gateway_action(qapp):
    _ = qapp

    class GatewayActionChatService(DummyChatService):
        def __init__(self, messages: QAbstractListModel) -> None:
            super().__init__(messages)
            self.start_calls = 0

        @Property(str, constant=True)
        def state(self) -> str:
            return "idle"

        @Slot()
        def start(self) -> None:
            self.start_calls += 1

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    chat_service = GatewayActionChatService(EmptyMessagesModel())
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        capsule = _find_object(root, "gatewayCapsule")
        capsule.forceActiveFocus()
        _process(20)

        assert bool(capsule.property("activeFocus")) is True

        QTest.keyClick(root, Qt.Key_Space)
        _process(20)

        assert chat_service.start_calls == 1
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_gateway_detail_bubble_is_overlay_child_of_capsule(qapp):
    _ = qapp

    class GatewayErrorChatService(DummyChatService):
        def __init__(self, messages: QAbstractListModel) -> None:
            super().__init__(messages)
            self._gateway_detail_value = "⚠ Channel start failed: telegram: bad token"

        @Property(str, constant=True)
        def gatewayDetail(self) -> str:
            return self._gateway_detail_value

        @Property(bool, constant=True)
        def gatewayDetailIsError(self) -> bool:
            return True

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    chat_service = GatewayErrorChatService(EmptyMessagesModel())
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        orb = _find_object(root, "gatewayDetailOrb")
        bubble = _find_object(root, "gatewayDetailBubble")
        capsule = _find_object(root, "gatewayCapsule")

        assert bool(orb.property("visible")) is True
        assert bool(bubble.property("visible")) is False
        capsule.forceActiveFocus()
        _process(20)
        QTest.mouseMove(root, _center_point(capsule))
        _process(40)
        assert bool(bubble.property("visible")) is True
        assert bubble.parent().objectName() == "gatewayStatusOrb"
        assert float(bubble.property("y")) >= float(orb.property("y"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_gateway_detail_bubble_caps_long_error_height_and_scrolls(qapp):
    _ = qapp

    class GatewayLongErrorChatService(DummyChatService):
        def __init__(self, messages: QAbstractListModel) -> None:
            super().__init__(messages)
            self._gateway_detail_value = " ".join(["telegram bad token"] * 40)

        @Property(str, constant=True)
        def gatewayDetail(self) -> str:
            return self._gateway_detail_value

        @Property(bool, constant=True)
        def gatewayDetailIsError(self) -> bool:
            return True

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    chat_service = GatewayLongErrorChatService(EmptyMessagesModel())
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        orb = _find_object(root, "gatewayDetailOrb")
        bubble = _find_object(root, "gatewayDetailBubble")
        viewport = _find_object(root, "gatewayDetailViewport")

        assert bool(orb.property("visible")) is True
        QTest.mouseMove(root, QPoint(0, 0))
        _process(20)
        QTest.mouseMove(root, _center_point(orb))
        _process(40)

        assert bool(bubble.property("visible")) is True
        assert float(bubble.property("height")) <= 134.0
        assert bool(viewport.property("interactive")) is True
        assert float(viewport.property("contentHeight")) > float(viewport.property("height"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_gateway_detail_orb_shows_overflow_badge_for_many_channels(qapp):
    _ = qapp

    class GatewayChannelsChatService(DummyChatService):
        @Property(list, constant=True)
        def gatewayChannels(self) -> list[dict[str, object]]:
            return [
                {"channel": "telegram", "state": "running", "detail": ""},
                {"channel": "imessage", "state": "running", "detail": ""},
                {"channel": "email", "state": "idle", "detail": ""},
            ]

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    chat_service = GatewayChannelsChatService(EmptyMessagesModel())
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        orb = _find_object(root, "gatewayDetailOrb")
        overflow = _find_object(root, "gatewayDetailOrbOverflow")

        assert bool(orb.property("visible")) is True
        assert bool(overflow.property("visible")) is True
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_gateway_detail_orb_uses_pill_shape_for_multiple_channels(qapp):
    _ = qapp

    class GatewayChannelsChatService(DummyChatService):
        @Property(list, constant=True)
        def gatewayChannels(self) -> list[dict[str, object]]:
            return [
                {"channel": "telegram", "state": "running", "detail": ""},
                {"channel": "imessage", "state": "running", "detail": ""},
            ]

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    chat_service = GatewayChannelsChatService(EmptyMessagesModel())
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        orb = _find_object(root, "gatewayDetailOrb")

        assert bool(orb.property("visible")) is True
        assert float(orb.property("width")) > float(orb.property("height"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_gateway_detail_bubble_width_adapts_for_short_summary(qapp):
    _ = qapp

    class GatewaySummaryChatService(DummyChatService):
        def __init__(self, messages: QAbstractListModel) -> None:
            super().__init__(messages)
            self._gateway_detail_value = "短摘要"

        @Property(str, constant=True)
        def gatewayDetail(self) -> str:
            return self._gateway_detail_value

        @Property(bool, constant=True)
        def gatewayDetailIsError(self) -> bool:
            return False

    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    chat_service = GatewaySummaryChatService(EmptyMessagesModel())
    engine, root = _load_main_window(session_model=session_model, chat_service=chat_service)

    try:
        bubble = _find_object(root, "gatewayDetailBubble")
        orb = _find_object(root, "gatewayDetailOrb")

        QTest.mouseMove(root, QPoint(0, 0))
        _process(20)
        QTest.mouseMove(root, _center_point(orb))
        _process(40)

        assert bool(bubble.property("visible")) is True
        assert float(bubble.property("width")) < 248.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


@pytest.mark.parametrize(
    ("ok", "error", "expected_success", "expected_fragment"),
    [
        (True, "", True, "Session deleted"),
        (False, "boom", False, "boom"),
    ],
)
def test_delete_toast_waits_for_delete_completed(
    qapp,
    ok: bool,
    error: str,
    expected_success: bool,
    expected_fragment: str,
):
    _ = qapp
    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            }
        ]
    )
    engine, root = _load_main_window(session_model=session_model)

    try:
        sidebar = _find_object(root, "appSidebar")
        session_service = engine._test_refs["session_service"]
        toast = _find_toast(root)

        sidebar.sessionDeleteRequested.emit("desktop:local::default")
        _process(20)

        assert session_service.delete_session_calls == ["desktop:local::default"]
        assert toast.property("message") == ""

        session_service.deleteCompleted.emit("desktop:local::default", ok, error)
        _process(20)

        assert toast.property("message") != ""
        assert bool(toast.property("success")) is expected_success
        assert expected_fragment in str(toast.property("message"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_header_unread_badge_aggregates_unread_sessions(qapp):
    _ = qapp
    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": True,
            },
            {
                "key": "telegram:room1",
                "title": "Telegram",
                "updated_at": "2026-03-06T10:01:00",
                "channel": "telegram",
                "has_unread": True,
            },
            {
                "key": "system",
                "title": "System",
                "updated_at": "2026-03-06T10:02:00",
                "channel": "system",
                "has_unread": False,
            },
        ]
    )
    engine, root = _load_main_window(session_model=session_model)

    try:
        session_service = engine._test_refs["session_service"]
        badge = _find_object(root, "sessionsHeaderUnreadBadge")
        badge_text = _find_object(root, "sessionsHeaderUnreadText")

        session_service.sessionsChanged.emit()

        for _ in range(4):
            _process(30)

        assert bool(badge.property("visible")) is True
        assert str(badge_text.property("text")) == "2"
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_header_unread_badge_drops_active_session_immediately(qapp):
    _ = qapp
    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            },
            {
                "key": "telegram:room1",
                "title": "Telegram",
                "updated_at": "2026-03-06T10:01:00",
                "channel": "telegram",
                "has_unread": True,
            },
        ]
    )
    engine, root = _load_main_window(session_model=session_model)

    try:
        session_service = engine._test_refs["session_service"]
        badge = _find_object(root, "sessionsHeaderUnreadBadge")
        badge_text = _find_object(root, "sessionsHeaderUnreadText")

        session_service.sessionsChanged.emit()
        for _ in range(4):
            _process(30)

        assert bool(badge.property("visible")) is True
        assert str(badge_text.property("text")) == "1"

        session_service.setActiveKey("telegram:room1")
        for _ in range(2):
            _process(30)

        assert bool(badge.property("visible")) is False
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_unread_does_not_revive_after_switching_away(qapp):
    _ = qapp
    session_model = SessionsModel(
        [
            {
                "key": "desktop:local::default",
                "title": "Default",
                "updated_at": "2026-03-06T10:00:00",
                "channel": "desktop",
                "has_unread": False,
            },
            {
                "key": "telegram:room1",
                "title": "Telegram",
                "updated_at": "2026-03-06T10:01:00",
                "channel": "telegram",
                "has_unread": True,
            },
        ]
    )
    engine, root = _load_main_window(session_model=session_model)

    try:
        session_service = engine._test_refs["session_service"]
        badge = _find_object(root, "sessionsHeaderUnreadBadge")

        session_service.sessionsChanged.emit()
        _process(40)
        session_service.setActiveKey("telegram:room1")
        _process(40)
        session_service.setActiveKey("desktop:local::default")
        _process(40)

        assert bool(badge.property("visible")) is False
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_delete_above_viewport_preserves_visible_anchor(qapp):
    _ = qapp
    rows = []
    for i in range(12):
        rows.append(
            {
                "key": f"desktop:local::s{i}",
                "title": f"Session {i}",
                "updated_at": f"2026-03-06T10:{i:02d}:00",
                "channel": "desktop",
                "has_unread": False,
            }
        )
    session_model = SessionsModel(rows)
    engine, root = _load_main_window(session_model=session_model)

    try:
        session_service = engine._test_refs["session_service"]
        session_list = _find_object(root, "sidebarSessionList")

        session_service.sessionsChanged.emit()
        for _ in range(4):
            _process(30)

        session_list.setProperty("contentY", 220)
        _process(30)
        before_key, before_offset = _first_visible_sidebar_session_anchor(root, session_list)
        before_y = float(session_list.property("contentY"))

        session_model.replaceRows(rows[1:])
        session_service.sessionsChanged.emit()
        for _ in range(4):
            _process(30)

        after_offset = _sidebar_session_anchor_offset(session_list, before_key)
        after_y = float(session_list.property("contentY"))
        origin_y = float(session_list.property("originY"))
        assert isinstance(before_offset, float)
        assert isinstance(after_offset, float)
        assert after_y <= before_y + 0.5
        assert after_y >= origin_y
        assert abs(after_offset - before_offset) < 2.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_active_session_reorder_does_not_jump_to_top(qapp):
    _ = qapp
    rows = []
    for i in range(20):
        rows.append(
            {
                "key": f"imessage:chat::{i}",
                "title": f"Chat {i}",
                "updated_at": f"2026-03-06T10:{59 - i:02d}:00",
                "channel": "imessage",
                "has_unread": False,
            }
        )
    session_model = SessionsModel(rows)
    engine, root = _load_main_window(session_model=session_model)

    try:
        session_service = engine._test_refs["session_service"]
        session_list = _find_object(root, "sidebarSessionList")

        session_service.setActiveKey("imessage:chat::15")
        session_service.sessionsChanged.emit()
        for _ in range(4):
            _process(30)

        max_y_before = max(
            0.0,
            float(session_list.property("contentHeight")) - float(session_list.property("height")),
        )
        session_list.setProperty("contentY", max_y_before)
        _process(30)
        before_y = float(session_list.property("contentY"))
        origin_y = float(session_list.property("originY"))
        assert before_y > origin_y + 100.0
        active_y_before = _sidebar_delegate_y(session_list, "imessage:chat::15")
        assert active_y_before < before_y + float(session_list.property("height"))

        reordered_rows = [dict(row) for row in rows]
        active_row = reordered_rows.pop(15)
        active_row["updated_at"] = "2026-03-06T11:59:00"
        reordered_rows.insert(0, active_row)

        session_model.replaceRows(reordered_rows)
        session_service.sessionsChanged.emit()
        for _ in range(4):
            _process(30)

        after_y = float(session_list.property("contentY"))
        assert after_y > origin_y + 100.0
        assert abs(after_y - before_y) < 40.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_sticky_header_tracks_scrolled_group(qapp):
    _ = qapp
    rows = []
    for i in range(12):
        rows.append(
            {
                "key": f"desktop:local::s{i}",
                "title": f"Desktop {i}",
                "updated_at": f"2026-03-06T10:{i:02d}:00",
                "channel": "desktop",
                "has_unread": False,
            }
        )
    for i in range(12):
        rows.append(
            {
                "key": f"telegram:room{i}",
                "title": f"Telegram {i}",
                "updated_at": f"2026-03-06T11:{i:02d}:00",
                "channel": "telegram",
                "has_unread": i == 0,
                "is_running": i == 8,
            }
        )
    session_model = SessionsModel(rows)
    engine, root = _load_main_window(session_model=session_model)

    try:
        session_service = engine._test_refs["session_service"]
        session_list = _find_object(root, "sidebarSessionList")
        sticky = _find_object(root, "sidebarStickyHeader")
        sticky_viewport = _find_object(root, "sidebarStickyHeaderViewport")

        session_service.setActiveKey("telegram:room8")
        session_service.sessionsChanged.emit()
        for _ in range(4):
            _process(30)

        max_y_before = max(
            0.0,
            float(session_list.property("contentHeight")) - float(session_list.property("height")),
        )
        session_list.setProperty("contentY", max_y_before)
        for _ in range(4):
            _process(30)

        assert bool(sticky.property("visible")) is True
        assert sticky.property("channel") == "telegram"
        assert bool(sticky.property("groupHasRunning")) is True
        assert float(sticky_viewport.property("y")) >= float(session_list.property("y")) - 1.0
        assert float(sticky_viewport.property("y")) <= float(session_list.property("y")) + 1.0
        assert float(sticky.property("y")) >= -float(sticky.property("height")) - 1.0
        assert float(sticky.property("y")) <= 1.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_session_delegate_geometry_contains_row_spacing(qapp):
    _ = qapp
    rows = []
    for i in range(10):
        rows.append(
            {
                "key": f"desktop:local::s{i}",
                "title": f"Desktop {i}",
                "updated_at": f"2026-03-06T10:{i:02d}:00",
                "channel": "desktop",
                "has_unread": False,
            }
        )
    session_model = SessionsModel(rows)
    engine, root = _load_main_window(session_model=session_model)

    try:
        session_service = engine._test_refs["session_service"]
        session_service.setActiveKey("desktop:local::s0")
        session_service.sessionsChanged.emit()
        for _ in range(4):
            _process(30)

        session_list = _find_object(root, "sidebarSessionList")
        delegate = _sidebar_delegate_root(session_list, "desktop:local::s0")
        child_bottom = 0.0
        for child in delegate.childItems():
            if not bool(child.property("visible")):
                continue
            child_bottom = max(
                child_bottom, float(child.property("y")) + float(child.property("height"))
            )

        assert child_bottom <= float(delegate.property("height")) + 0.5
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_sidebar_near_bottom_refresh_keeps_visible_anchor(qapp):
    _ = qapp
    rows = []
    for i in range(30):
        rows.append(
            {
                "key": f"imessage:chat::{i}",
                "title": f"Chat {i}",
                "updated_at": f"2026-03-06T10:{59 - (i % 60):02d}:00",
                "channel": "imessage",
                "has_unread": False,
            }
        )
    session_model = SessionsModel(rows)
    engine, root = _load_main_window(session_model=session_model)

    try:
        session_service = engine._test_refs["session_service"]
        session_list = _find_object(root, "sidebarSessionList")

        session_service.setActiveKey("imessage:chat::25")
        session_service.sessionsChanged.emit()
        for _ in range(4):
            _process(30)

        max_y_before = max(
            0.0,
            float(session_list.property("contentHeight")) - float(session_list.property("height")),
        )
        session_list.setProperty("contentY", max_y_before)
        _process(30)

        current_rows = [dict(row) for row in rows]
        for step in range(3):
            moved = current_rows.pop(24 - step)
            moved["updated_at"] = f"2026-03-06T11:5{step}:00"
            current_rows.insert(0, moved)

            session_model.replaceRows(current_rows)
            session_service.sessionsChanged.emit()
            session_service.sessionsChanged.emit()
            for _ in range(6):
                _process(30)

            content_y = float(session_list.property("contentY"))
            origin_y = float(session_list.property("originY"))
            max_y = max(
                0.0,
                float(session_list.property("contentHeight"))
                - float(session_list.property("height")),
            )
            key, _offset = _first_visible_sidebar_session_anchor(root, session_list)

            assert key != ""
            assert content_y >= origin_y
            assert content_y <= max_y + 2.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_system_message_append_forces_follow_to_end(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    messages_model = ChatMessageModel()
    for i in range(48):
        messages_model.append_user(f"message {i}")

    engine, root = _load_main_window(messages_model=messages_model)

    try:
        chat_service = engine._test_refs["chat_service"]
        message_list = _find_object(root, "chatMessageList")

        for _ in range(6):
            _process(30)

        max_y_before = max(
            0.0,
            float(message_list.property("contentHeight")) - float(message_list.property("height")),
        )
        assert max_y_before > 1.0

        _ = message_list.setProperty("contentY", 0.0)
        _process(30)

        row = messages_model.append_system(
            "Gateway started", entrance_style="system", entrance_pending=True
        )
        chat_service.messageAppended.emit(row)

        for _ in range(8):
            _process(30)

        max_y_after = max(
            0.0,
            float(message_list.property("contentHeight")) - float(message_list.property("height")),
        )
        follow_upper_bound = max_y_after + float(message_list.property("topMargin")) + 2.0
        content_y = float(message_list.property("contentY"))

        assert max_y_after > 1.0
        assert content_y >= max_y_after - 2.0
        assert content_y <= follow_upper_bound
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


@pytest.mark.parametrize(
    ("append_message", "label"),
    [
        (lambda model: model.append_user("hello"), "user"),
        (lambda model: model.append_assistant("hello", status="done"), "assistant"),
        (
            lambda model: model.append_system(
                "Gateway started", entrance_style="system", entrance_pending=True
            ),
            "system",
        ),
        (
            lambda model: model.append_system(
                "Welcome back", entrance_style="greeting", entrance_pending=True
            ),
            "greeting",
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_main_chat_view_appended_messages_force_follow_to_end(qapp, append_message, label):
    _ = qapp
    _ = label
    from app.backend.chat import ChatMessageModel

    messages_model = ChatMessageModel()
    for i in range(48):
        messages_model.append_user(f"message {i}")

    engine, root = _load_main_window(messages_model=messages_model)

    try:
        chat_service = engine._test_refs["chat_service"]
        message_list = _find_object(root, "chatMessageList")

        for _ in range(6):
            _process(30)

        max_y_before = max(
            0.0,
            float(message_list.property("contentHeight")) - float(message_list.property("height")),
        )
        assert max_y_before > 1.0

        _ = message_list.setProperty("contentY", 0.0)
        _process(30)

        row = append_message(messages_model)
        chat_service.messageAppended.emit(row)

        for _ in range(8):
            _process(30)

        max_y_after = max(
            0.0,
            float(message_list.property("contentHeight")) - float(message_list.property("height")),
        )
        follow_upper_bound = max_y_after + float(message_list.property("topMargin")) + 2.0
        content_y = float(message_list.property("contentY"))

        assert max_y_after > 1.0
        assert content_y >= max_y_after - 2.0
        assert content_y <= follow_upper_bound
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_deferred_follow_respects_history_loading(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    messages_model = ChatMessageModel()
    for i in range(48):
        messages_model.append_user(f"message {i}")

    engine, root = _load_main_window(messages_model=messages_model)

    try:
        chat_service = engine._test_refs["chat_service"]
        message_list = _find_object(root, "chatMessageList")

        for _ in range(6):
            _process(30)

        row = messages_model.append_system(
            "Gateway started", entrance_style="system", entrance_pending=True
        )
        chat_service.messageAppended.emit(row)

        _ = message_list.setProperty("contentY", 0.0)
        chat_service.setHistoryLoading(True)

        for _ in range(4):
            _process(30)

        assert float(message_list.property("contentY")) < 2.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_history_merge_with_tool_row_and_final_result_does_not_jump_to_top(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    raw_history = [{"role": "user", "content": f"message {i}"} for i in range(48)]
    messages_model = ChatMessageModel()
    messages_model.load_prepared(
        ChatMessageModel.prepare_history(
            raw_history
            + [
                {"role": "assistant", "content": "working", "status": "done"},
                {"role": "assistant", "content": "", "status": "typing"},
            ]
        )
    )

    engine, root = _load_main_window(messages_model=messages_model)

    try:
        message_list = _find_object(root, "chatMessageList")

        for _ in range(6):
            _process(30)

        max_y_before = max(
            0.0,
            float(message_list.property("contentHeight")) - float(message_list.property("height")),
        )
        assert max_y_before > 1.0

        _ = message_list.setProperty("contentY", max_y_before)
        _process(30)

        prepared = ChatMessageModel.prepare_history(
            raw_history
            + [
                {"role": "tool", "content": "running tool"},
                {"role": "assistant", "content": "final", "status": "done", "format": "markdown"},
            ]
        )
        messages_model.load_prepared(prepared, preserve_transient_tail=True)

        for _ in range(6):
            _process(30)

        content_y = float(message_list.property("contentY"))
        assert content_y > 2.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_history_merge_after_send_result_does_not_jump_to_top(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    raw_history = [{"role": "user", "content": f"message {i}"} for i in range(48)]
    messages_model = ChatMessageModel()
    messages_model.load_prepared(
        ChatMessageModel.prepare_history(
            raw_history
            + [
                {"role": "assistant", "content": "working", "status": "done"},
                {"role": "assistant", "content": "final", "status": "done", "format": "markdown"},
            ]
        )
    )

    engine, root = _load_main_window(messages_model=messages_model)

    try:
        message_list = _find_object(root, "chatMessageList")

        for _ in range(6):
            _process(30)

        max_y_before = max(
            0.0,
            float(message_list.property("contentHeight")) - float(message_list.property("height")),
        )
        assert max_y_before > 1.0

        _ = message_list.setProperty("contentY", max_y_before)
        _process(30)

        prepared = ChatMessageModel.prepare_history(
            raw_history
            + [
                {"role": "tool", "content": "running tool"},
                {"role": "assistant", "content": "final", "status": "done", "format": "markdown"},
            ]
        )
        messages_model.load_prepared(prepared)

        for _ in range(6):
            _process(30)

        content_y = float(message_list.property("contentY"))
        assert content_y > 2.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_preserves_viewport_on_model_reset(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    messages_model = ChatMessageModel()
    messages_model.load_prepared(
        ChatMessageModel.prepare_history(
            [{"role": "user", "content": f"message {i}"} for i in range(72)]
        )
    )

    engine, root = _load_main_window(messages_model=messages_model)

    try:
        message_list = _find_object(root, "chatMessageList")

        for _ in range(6):
            _process(30)

        max_y_before = max(
            0.0,
            float(message_list.property("contentHeight")) - float(message_list.property("height")),
        )
        assert max_y_before > 20.0

        target_y = max_y_before / 2.0
        _ = message_list.setProperty("contentY", target_y)
        _process(30)

        messages_model.load_prepared(
            ChatMessageModel.prepare_history(
                [{"role": "assistant", "content": f"reply {i}"} for i in range(72)]
            )
        )

        for _ in range(6):
            _process(30)

        content_y = float(message_list.property("contentY"))
        assert content_y > 20.0
        assert abs(content_y - target_y) < 24.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_keyboard_shortcuts_scroll_history(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    messages_model = ChatMessageModel()
    messages_model.load_prepared(
        ChatMessageModel.prepare_history(
            [{"role": "user", "content": f"message {i}"} for i in range(72)]
        )
    )

    engine, root = _load_main_window(messages_model=messages_model)

    try:
        message_input = _find_object(root, "chatMessageInput")
        message_list = _find_object(root, "chatMessageList")
        root.requestActivate()

        for _ in range(6):
            _process(30)

        max_y = max(
            0.0,
            float(message_list.property("contentHeight")) - float(message_list.property("height")),
        )
        assert max_y > 20.0

        _ = message_list.setProperty("contentY", 0.0)
        message_list.forceActiveFocus()
        _process(20)

        for _ in range(2):
            QTest.keyClick(root, Qt.Key_Down)
            _process(30)
            if float(message_list.property("contentY")) > 0.0:
                break
            root.requestActivate()
            message_list.forceActiveFocus()
            _process(20)

        scrolled_down = float(message_list.property("contentY"))
        assert scrolled_down > 0.0

        for _ in range(2):
            QTest.keyClick(root, Qt.Key_Up)
            _process(30)
            if float(message_list.property("contentY")) < scrolled_down:
                break
            root.requestActivate()
            message_list.forceActiveFocus()
            _process(20)

        scrolled_up = float(message_list.property("contentY"))
        assert scrolled_up < scrolled_down

        message_input.forceActiveFocus()
        _process(20)
        _ = message_list.setProperty("contentY", 0.0)
        _process(20)

        QTest.keyClick(root, Qt.Key_Down)
        _process(30)

        assert float(message_list.property("contentY")) < 1.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_keyboard_scroll_respects_list_bounds(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    messages_model = ChatMessageModel()
    messages_model.load_prepared(
        ChatMessageModel.prepare_history(
            [{"role": "user", "content": f"message {i}"} for i in range(96)]
        )
    )

    engine, root = _load_main_window(messages_model=messages_model)

    try:
        message_list = _find_object(root, "chatMessageList")
        root.requestActivate()

        for _ in range(6):
            _process(30)

        message_list.forceActiveFocus()
        _process(20)

        QTest.keyClick(root, Qt.Key_End)
        _process(40)
        bottom_y = float(message_list.property("contentY"))

        QTest.keyClick(root, Qt.Key_Down)
        _process(30)
        QTest.keyClick(root, Qt.Key_PageDown)
        _process(30)

        assert abs(float(message_list.property("contentY")) - bottom_y) < 2.0

        for _ in range(160):
            QTest.keyClick(root, Qt.Key_Up)
            _process(8)

        QTest.keyClick(root, Qt.Key_Home)
        _process(40)
        top_y = float(message_list.property("contentY"))

        QTest.keyClick(root, Qt.Key_Up)
        _process(30)
        QTest.keyClick(root, Qt.Key_PageUp)
        _process(30)

        assert abs(float(message_list.property("contentY")) - top_y) < 2.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_active_session_switch_follows_to_end_after_reset(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    messages_model = ChatMessageModel()
    messages_model.load_prepared(
        ChatMessageModel.prepare_history(
            [{"role": "user", "content": f"message {i}"} for i in range(72)]
        )
    )

    engine, root = _load_main_window(messages_model=messages_model)

    try:
        chat_service = engine._test_refs["chat_service"]
        message_list = _find_object(root, "chatMessageList")
        session_service = engine._test_refs["session_service"]

        for _ in range(6):
            _process(30)

        _ = message_list.setProperty("contentY", 0.0)
        _process(20)

        session_service.setActiveKey("desktop:local::other")
        messages_model.load_prepared(
            ChatMessageModel.prepare_history(
                [{"role": "assistant", "content": f"reply {i}"} for i in range(72)]
            )
        )
        chat_service.emitSessionViewApplied("desktop:local::other")

        for _ in range(12):
            _process(30)
            max_y = max(
                0.0,
                float(message_list.property("contentHeight"))
                - float(message_list.property("height")),
            )
            content_y = float(message_list.property("contentY"))
            if max_y <= 20.0 or content_y < max_y - 2.0:
                continue
            break

        max_y = max(
            0.0,
            float(message_list.property("contentHeight")) - float(message_list.property("height")),
        )
        follow_lower_bound = max_y - float(message_list.property("topMargin")) - 2.0
        follow_upper_bound = max_y + float(message_list.property("topMargin")) + 2.0
        content_y = float(message_list.property("contentY"))

        assert max_y > 20.0
        assert content_y >= follow_lower_bound
        assert content_y <= follow_upper_bound
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_render_equivalent_session_switch_keeps_future_restore(qapp):
    _ = qapp
    from app.backend.chat import ChatMessageModel

    prepared = ChatMessageModel.prepare_history(
        [{"role": "user", "content": f"message {i}"} for i in range(72)]
    )
    messages_model = ChatMessageModel()
    messages_model.load_prepared(prepared)

    engine, root = _load_main_window(messages_model=messages_model)

    try:
        chat_service = engine._test_refs["chat_service"]
        session_service = engine._test_refs["session_service"]
        message_list = _find_object(root, "chatMessageList")

        for _ in range(6):
            _process(30)

        session_service.setActiveKey("desktop:local::other")
        chat_service.setHistoryLoading(True)
        messages_model.load_prepared(prepared)
        chat_service.emitSessionViewApplied("desktop:local::other")
        _process(20)
        chat_service.setHistoryLoading(False)

        for _ in range(8):
            _process(30)

        max_y = max(
            0.0,
            float(message_list.property("contentHeight")) - float(message_list.property("height")),
        )
        assert max_y > 20.0

        target_y = max_y / 2.0
        _ = message_list.setProperty("contentY", target_y)
        _process(30)

        messages_model.load_prepared(
            ChatMessageModel.prepare_history(
                [{"role": "assistant", "content": f"reply {i}"} for i in range(72)]
            )
        )

        for _ in range(8):
            _process(30)

        content_y = float(message_list.property("contentY"))
        assert abs(content_y - target_y) < 24.0
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)
