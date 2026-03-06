# ruff: noqa: E402, N802, N815

from __future__ import annotations

import importlib
import sys
from pathlib import Path

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QtGui = pytest.importorskip("PySide6.QtGui")
QtQml = pytest.importorskip("PySide6.QtQml")
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


class DummyChatService(QObject):
    historyLoadingChanged = Signal(bool)
    messageAppended = Signal(int)
    statusUpdated = Signal(int, str)
    gatewayReady = Signal(bool)

    def __init__(self, messages: QAbstractListModel, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._messages = messages
        self._history_loading = False

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
        return "running"

    @Property(str, constant=True)
    def lastError(self) -> str:
        return ""

    @Property(str, constant=True)
    def gatewayDetail(self) -> str:
        return ""

    @Property(bool, constant=True)
    def gatewayDetailIsError(self) -> bool:
        return False

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
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._is_valid = is_valid
        self._needs_setup = needs_setup
        self._language = language
        self._ui_update: dict[str, object] = {}
        self._providers: list[dict[str, object]] = [dict(item) for item in (providers or [])]
        self._agents_defaults: dict[str, object] = {}
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


class DummySessionService(QObject):
    sessionsChanged = Signal()
    activeKeyChanged = Signal(str)
    deleteCompleted = Signal(str, bool, str)
    activeReady = Signal()

    def __init__(self, sessions_model: QAbstractListModel, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sessions_model = sessions_model
        self.new_session_calls: list[str] = []
        self.select_session_calls: list[str] = []
        self.delete_session_calls: list[str] = []

    @Property(str, constant=True)
    def activeKey(self) -> str:
        return ""

    @Property(QObject, constant=True)
    def sessionsModel(self) -> QObject:
        return self._sessions_model

    @Slot(str)
    def newSession(self, name: str) -> None:
        self.new_session_calls.append(name)

    @Slot(str)
    def selectSession(self, key: str) -> None:
        self.select_session_calls.append(key)

    @Slot(str)
    def deleteSession(self, key: str) -> None:
        self.delete_session_calls.append(key)


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
) -> tuple[QQmlApplicationEngine, QObject]:
    messages_model = messages_model or EmptyMessagesModel()
    chat_service = chat_service or DummyChatService(messages_model)
    config_service = config_service or DummyConfigService()
    session_service = DummySessionService(session_model or messages_model)
    update_service = DummyUpdateService()
    update_bridge = DummyUpdateBridge()
    theme_manager = QObject()
    clipboard_service = QObject()
    engine = QQmlApplicationEngine()
    engine._test_refs = {
        "messages_model": messages_model,
        "chat_service": chat_service,
        "config_service": config_service,
        "session_service": session_service,
        "update_service": update_service,
        "update_bridge": update_bridge,
        "theme_manager": theme_manager,
        "clipboard_service": clipboard_service,
    }
    context = engine.rootContext()
    context.setContextProperty("chatService", chat_service)
    context.setContextProperty("configService", config_service)
    context.setContextProperty("sessionService", session_service)
    context.setContextProperty("updateService", update_service)
    context.setContextProperty("updateBridge", update_bridge)
    context.setContextProperty("themeManager", theme_manager)
    context.setContextProperty("clipboardService", clipboard_service)
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


def _center_point(item: QObject) -> QPoint:
    center = item.mapToScene(QPointF(item.property("width") / 2, item.property("height") / 2))
    return QPoint(int(center.x()), int(center.y()))


def test_main_chat_view_composer_click_focus_works_with_window_focus_filter(qapp):
    _ = qapp
    engine, root = _load_main_window()

    try:
        focus_filter = WindowFocusDismissFilter(root)
        root.installEventFilter(focus_filter)
        message_input = _find_chat_input(root)

        message_input.forceActiveFocus()
        _process(0)
        assert bool(message_input.property("activeFocus")) is True

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, _center_point(message_input))
        _process(0)

        assert bool(message_input.property("activeFocus")) is True
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_main_chat_view_external_click_clears_selection_with_window_focus_filter(qapp):
    _ = qapp
    engine, root = _load_main_window()

    try:
        focus_filter = WindowFocusDismissFilter(root)
        root.installEventFilter(focus_filter)
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


def test_onboarding_invalid_ui_language_stays_on_first_step(qapp):
    _ = qapp
    config_service = DummyConfigService(is_valid=False, needs_setup=True, language="fr")
    engine, root = _load_main_window(config_service)

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
        bubble = _find_object(root, "gatewayDetailBubble")
        text = _find_object(root, "gatewayDetailText")

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
        capsule = _find_object(root, "gatewayCapsule")

        assert bool(bubble.property("visible")) is False

        QTest.mouseMove(root, QPoint(0, 0))
        _process(20)
        QTest.mouseMove(root, _center_point(capsule))
        _process(40)
        if not bool(bubble.property("visible")):
            QTest.mouseMove(root, _center_point(capsule))
            _process(40)

        assert bool(bubble.property("visible")) is True
        assert "Gateway started" in str(text.property("text"))
    finally:
        root.deleteLater()
        engine.deleteLater()
        _process(0)


def test_gateway_detail_bubble_shows_summary_on_focus(qapp):
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
        capsule = _find_object(root, "gatewayCapsule")

        assert bool(bubble.property("visible")) is False
        capsule.forceActiveFocus()
        _process(20)

        assert bool(capsule.property("activeFocus")) is True
        assert bool(bubble.property("visible")) is True
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
        bubble = _find_object(root, "gatewayDetailBubble")
        capsule = _find_object(root, "gatewayCapsule")

        assert bool(bubble.property("visible")) is True
        assert bubble.parent() is capsule
        assert float(bubble.property("y")) <= float(capsule.property("height"))
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
        bubble = _find_object(root, "gatewayDetailBubble")
        viewport = _find_object(root, "gatewayDetailViewport")

        assert bool(bubble.property("visible")) is True
        assert float(bubble.property("height")) <= 134.0
        assert bool(viewport.property("interactive")) is True
        assert float(viewport.property("contentHeight")) > float(viewport.property("height"))
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
        content_y = float(message_list.property("contentY"))

        assert max_y_after > 1.0
        assert content_y >= max_y_after - 2.0
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
        content_y = float(message_list.property("contentY"))

        assert max_y_after > 1.0
        assert content_y >= max_y_after - 2.0
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
