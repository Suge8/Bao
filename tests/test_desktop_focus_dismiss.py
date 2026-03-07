# ruff: noqa: E402, N802

from __future__ import annotations

import importlib
import sys
from pathlib import Path

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QtGui = pytest.importorskip("PySide6.QtGui")
QtQml = pytest.importorskip("PySide6.QtQml")
QtTest = pytest.importorskip("PySide6.QtTest")

QEvent = QtCore.QEvent
QCoreApplication = QtCore.QCoreApplication
QEventLoop = QtCore.QEventLoop
QObject = QtCore.QObject
QPoint = QtCore.QPoint
QPointF = QtCore.QPointF
QTimer = QtCore.QTimer
QUrl = QtCore.QUrl
Qt = QtCore.Qt
QGuiApplication = QtGui.QGuiApplication
QFont = QtGui.QFont
QMouseEvent = QtGui.QMouseEvent
QQmlComponent = QtQml.QQmlComponent
QQmlEngine = QtQml.QQmlEngine
QTest = QtTest.QTest

from app.main import (
    BUNDLED_APP_FONT_FAMILY_PREFIX,
    WindowFocusDismissFilter,
    resolve_app_font_family,
)


@pytest.fixture(scope="session")
def qapp():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    yield app


def _process(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _wait_until_ready(component: QQmlComponent, timeout_ms: int = 500) -> None:
    remaining = timeout_ms
    while component.status() == QQmlComponent.Loading and remaining > 0:
        _process(25)
        remaining -= 25


def _build_window() -> bytes:
    return b"""
import QtQuick 2.15
import QtQuick.Controls 2.15

ApplicationWindow {
    width: 400
    height: 240
    visible: true

    Item {
        anchors.fill: parent

        Rectangle {
            anchors.fill: parent
            color: "white"
        }

        TextArea {
            id: editor
            objectName: "editor"
            x: 40
            y: 40
            width: 200
            height: 80
            focus: true
            text: "hello bao"
        }
    }
}
"""


def _build_two_editor_window() -> bytes:
    return b"""
import QtQuick 2.15
import QtQuick.Controls 2.15

ApplicationWindow {
    width: 500
    height: 240
    visible: true

    Item {
        anchors.fill: parent

        Rectangle {
            anchors.fill: parent
            color: "white"
        }

        TextArea {
            id: editorA
            objectName: "editorA"
            x: 40
            y: 40
            width: 160
            height: 80
            text: "hello a"
        }

        TextArea {
            id: editorB
            objectName: "editorB"
            x: 240
            y: 40
            width: 160
            height: 80
            text: "hello b"
        }
    }
}
"""


def _build_editor_and_button_window() -> bytes:
    return b"""
import QtQuick 2.15
import QtQuick.Controls 2.15

ApplicationWindow {
    width: 520
    height: 240
    visible: true

    Item {
        anchors.fill: parent

        TextArea {
            id: editor
            objectName: "editor"
            x: 40
            y: 40
            width: 200
            height: 80
            text: "hello bao"
        }

        Button {
            id: button
            objectName: "button"
            x: 300
            y: 40
            width: 100
            height: 40
            text: "Go"
            focusPolicy: Qt.StrongFocus
        }
    }
}
"""


def _mouse_release(x: float, y: float) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(x, y),
        QPointF(x, y),
        QPointF(x, y),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )


class _MouseMoveRecorder(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.moves = 0

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is not None and event.type() == QEvent.Type.MouseMove:
            self.moves += 1
        return False


def test_window_focus_dismiss_blurs_editor_on_external_click(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(_build_window(), QUrl("inline:FocusDismissHarness.qml"))
    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        editor = root.findChild(QObject, "editor")
        assert editor is not None

        editor.forceActiveFocus()
        _process(0)
        assert bool(editor.property("activeFocus")) is True

        focus_filter = WindowFocusDismissFilter(root)
        _ = focus_filter.eventFilter(root, _mouse_release(10, 10))
        _process(0)

        assert bool(editor.property("activeFocus")) is False
    finally:
        root.deleteLater()
        _process(0)


def test_window_focus_dismiss_keeps_editor_focus_on_internal_click(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(_build_window(), QUrl("inline:FocusDismissHarness.qml"))
    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        editor = root.findChild(QObject, "editor")
        assert editor is not None

        editor.forceActiveFocus()
        _process(0)
        assert bool(editor.property("activeFocus")) is True

        focus_filter = WindowFocusDismissFilter(root)
        _ = focus_filter.eventFilter(root, _mouse_release(80, 70))
        _process(0)

        assert bool(editor.property("activeFocus")) is True
    finally:
        root.deleteLater()
        _process(0)


def test_window_focus_dismiss_preserves_single_click_editor_to_editor_focus_transfer(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(_build_two_editor_window(), QUrl("inline:TwoEditorFocusHarness.qml"))
    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        editor_a = root.findChild(QObject, "editorA")
        editor_b = root.findChild(QObject, "editorB")
        assert editor_a is not None
        assert editor_b is not None

        focus_filter = WindowFocusDismissFilter(root)
        root.installEventFilter(focus_filter)

        editor_a.forceActiveFocus()
        _process(0)
        assert bool(editor_a.property("activeFocus")) is True
        assert bool(editor_b.property("activeFocus")) is False

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, QPoint(260, 60))
        _process(0)

        assert bool(editor_a.property("activeFocus")) is False
        assert bool(editor_b.property("activeFocus")) is True
    finally:
        root.deleteLater()
        _process(0)


def test_window_focus_dismiss_clears_selection_when_clicking_focusable_non_editor(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(_build_editor_and_button_window(), QUrl("inline:EditorAndButtonHarness.qml"))
    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        editor = root.findChild(QObject, "editor")
        button = root.findChild(QObject, "button")
        assert editor is not None
        assert button is not None

        focus_filter = WindowFocusDismissFilter(root)
        root.installEventFilter(focus_filter)

        editor.forceActiveFocus()
        _process(0)
        editor.select(0, 5)
        _process(0)

        assert bool(editor.property("activeFocus")) is True
        assert str(editor.property("selectedText")) == "hello"

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, QPoint(320, 60))
        _process(0)

        assert bool(editor.property("activeFocus")) is False
        assert str(editor.property("selectedText")) == ""
        assert bool(button.property("activeFocus")) is True
    finally:
        root.deleteLater()
        _process(0)


def test_window_focus_dismiss_posts_pointer_refresh_after_mouse_release(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(_build_window(), QUrl("inline:FocusDismissHarness.qml"))
    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()
    recorder: _MouseMoveRecorder | None = None

    try:
        recorder = _MouseMoveRecorder()
        root.installEventFilter(recorder)

        focus_filter = WindowFocusDismissFilter(root)
        _ = focus_filter.eventFilter(root, _mouse_release(10, 10))
        _process(0)
        QCoreApplication.sendPostedEvents(root, QEvent.Type.MouseMove)
        _process(0)

        assert recorder.moves >= 1
    finally:
        if recorder is not None:
            root.removeEventFilter(recorder)
        root.deleteLater()
        _process(0)


def test_resolve_app_font_family_prefers_bundled_font(qapp):
    family = resolve_app_font_family()

    assert family is not None
    assert family.startswith(BUNDLED_APP_FONT_FAMILY_PREFIX)


def test_resolve_app_font_family_falls_back_when_bundled_font_missing(qapp, monkeypatch):
    _ = qapp
    monkeypatch.setattr("app.main.resolve_bundled_app_font_path", lambda: None)
    monkeypatch.setattr("app.main.preferred_system_font_family", lambda: "Segoe UI")

    assert resolve_app_font_family() == "Segoe UI"


def test_resolve_app_font_family_falls_back_when_font_registration_fails(qapp, monkeypatch):
    _ = qapp
    monkeypatch.setattr(
        "app.main.resolve_bundled_app_font_path", lambda: Path("/tmp/OPPO Sans.ttf")
    )
    monkeypatch.setattr("app.main.QFontDatabase.addApplicationFont", lambda _path: -1)
    monkeypatch.setattr("app.main.preferred_system_font_family", lambda: "Segoe UI")

    assert resolve_app_font_family() == "Segoe UI"


def test_resolve_app_font_family_falls_back_when_registered_font_has_no_family(qapp, monkeypatch):
    _ = qapp
    monkeypatch.setattr(
        "app.main.resolve_bundled_app_font_path", lambda: Path("/tmp/OPPO Sans.ttf")
    )
    monkeypatch.setattr("app.main.QFontDatabase.addApplicationFont", lambda _path: 1)
    monkeypatch.setattr("app.main.QFontDatabase.applicationFontFamilies", lambda _font_id: [])
    monkeypatch.setattr("app.main.preferred_system_font_family", lambda: "Segoe UI")

    assert resolve_app_font_family() == "Segoe UI"


def test_qml_control_inherits_application_font(qapp):
    family = resolve_app_font_family()
    assert family is not None

    original_font = qapp.font()
    qapp.setFont(QFont(family))
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        b"import QtQuick 2.15\nimport QtQuick.Controls 2.15\nControl { property string familyName: font.family }",
        QUrl("inline:FontHarness.qml"),
    )
    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        assert str(root.property("familyName")) == family
    finally:
        qapp.setFont(original_font)
        root.deleteLater()
        _process(0)
