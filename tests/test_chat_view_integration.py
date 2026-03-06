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


class EmptyMessagesModel(QAbstractListModel):
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0

    def data(
        self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)
    ) -> object | None:
        return None

    def roleNames(self) -> dict[int, QByteArray]:
        return {}


class DummyChatService(QObject):
    historyLoadingChanged = Signal(bool)
    messageAppended = Signal(int)
    statusUpdated = Signal(int, str)
    gatewayReady = Signal(bool)

    def __init__(self, messages: EmptyMessagesModel, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._messages = messages

    @Property(QObject, constant=True)
    def messages(self) -> QObject:
        return self._messages

    @Property(bool, constant=True)
    def historyLoading(self) -> bool:
        return False

    @Property(str, constant=True)
    def state(self) -> str:
        return "running"

    @Property(str, constant=True)
    def lastError(self) -> str:
        return ""

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
    stateChanged = Signal()

    @Property(bool, constant=True)
    def isValid(self) -> bool:
        return True

    @Property(bool, constant=True)
    def needsSetup(self) -> bool:
        return False

    @Slot(str, result="QVariant")
    def getValue(self, path: str) -> object | None:
        if path == "ui.language":
            return "en"
        if path == "ui":
            return {"language": "en", "update": {}}
        if path == "providers":
            return {}
        return None

    @Slot(result="QVariant")
    def getProviders(self) -> list[object]:
        return []

    @Slot("QVariant", result=bool)
    def save(self, changes: object) -> bool:
        _ = changes
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

    def __init__(self, sessions_model: EmptyMessagesModel, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sessions_model = sessions_model

    @Property(str, constant=True)
    def activeKey(self) -> str:
        return ""

    @Property(QObject, constant=True)
    def sessionsModel(self) -> QObject:
        return self._sessions_model

    @Slot(str)
    def newSession(self, name: str) -> None:
        _ = name

    @Slot(str)
    def selectSession(self, key: str) -> None:
        _ = key

    @Slot(str)
    def deleteSession(self, key: str) -> None:
        _ = key


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
        if obj.property("placeholderText") == "Message Bao…":
            return obj
    raise AssertionError("chat composer TextArea not found")


def _load_main_window() -> tuple[QObject, QObject]:
    messages_model = EmptyMessagesModel()
    chat_service = DummyChatService(messages_model)
    config_service = DummyConfigService()
    session_service = DummySessionService(messages_model)
    update_service = DummyUpdateService()
    theme_manager = QObject()
    clipboard_service = QObject()
    engine = QQmlApplicationEngine()
    engine._test_refs = {
        "messages_model": messages_model,
        "chat_service": chat_service,
        "config_service": config_service,
        "session_service": session_service,
        "update_service": update_service,
        "theme_manager": theme_manager,
        "clipboard_service": clipboard_service,
    }
    context = engine.rootContext()
    context.setContextProperty("chatService", chat_service)
    context.setContextProperty("configService", config_service)
    context.setContextProperty("sessionService", session_service)
    context.setContextProperty("updateService", update_service)
    context.setContextProperty("themeManager", theme_manager)
    context.setContextProperty("clipboardService", clipboard_service)
    context.setContextProperty("messagesModel", messages_model)
    context.setContextProperty("systemUiLanguage", "en")
    engine.load(
        QUrl.fromLocalFile(str(Path("/Users/sugeh/Documents/Project/Bao/app/qml/Main.qml")))
    )
    root_objects = engine.rootObjects()
    assert root_objects
    root = root_objects[0]
    for _ in range(5):
        _process(30)
    return engine, root


def _click_points_for_item(item: QObject) -> list[QPoint]:
    top_left = item.mapToScene(QPointF(3, 3))
    top_right = item.mapToScene(QPointF(item.property("width") - 3, 3))
    bottom_left = item.mapToScene(QPointF(3, item.property("height") - 3))
    bottom_right = item.mapToScene(QPointF(item.property("width") - 3, item.property("height") - 3))
    return [
        QPoint(int(top_left.x()), int(top_left.y())),
        QPoint(int(top_right.x()), int(top_right.y())),
        QPoint(int(bottom_left.x()), int(bottom_left.y())),
        QPoint(int(bottom_right.x()), int(bottom_right.y())),
    ]


def test_main_chat_view_composer_click_focus_works_with_window_focus_filter(qapp):
    _ = qapp
    engine, root = _load_main_window()

    try:
        focus_filter = WindowFocusDismissFilter(root)
        root.installEventFilter(focus_filter)
        message_input = _find_chat_input(root)

        for point in _click_points_for_item(message_input):
            QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, point)
            _process(0)
            assert bool(message_input.property("activeFocus")) is True
            _ = message_input.setProperty("focus", False)
            _process(0)
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
