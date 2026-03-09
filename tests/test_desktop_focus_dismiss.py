# ruff: noqa: E402, N802

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import cast

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QtGui = pytest.importorskip("PySide6.QtGui")
QtQml = pytest.importorskip("PySide6.QtQml")
QtQuick = pytest.importorskip("PySide6.QtQuick")
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
QQuickWindow = QtQuick.QQuickWindow
QTest = QtTest.QTest

from app.main import (
    BUNDLED_APP_FONT_FAMILY_PREFIX,
    WindowFocusDismissFilter,
    refresh_pointer_if_window_active,
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
            property bool baoClickAwayEditor: true
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
            property bool baoClickAwayEditor: true
            x: 40
            y: 40
            width: 160
            height: 80
            text: "hello a"
        }

        TextArea {
            id: editorB
            objectName: "editorB"
            property bool baoClickAwayEditor: true
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
            property bool baoClickAwayEditor: true
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


def _build_editor_and_mouse_area_window() -> bytes:
    return b"""
import QtQuick 2.15
import QtQuick.Controls 2.15

ApplicationWindow {
    id: root
    width: 520
    height: 260
    visible: true
    property bool clicked: false

    Item {
        anchors.fill: parent

        TextArea {
            id: editor
            objectName: "editor"
            property bool baoClickAwayEditor: true
            x: 40
            y: 40
            width: 200
            height: 80
            text: "hello bao"
        }

        Rectangle {
            id: clickTarget
            objectName: "clickTarget"
            x: 300
            y: 40
            width: 140
            height: 44
            radius: 10
            color: "#dddddd"

            MouseArea {
                anchors.fill: parent
                onClicked: root.clicked = true
            }
        }
    }
}
"""


def _build_editor_and_expand_header_window() -> bytes:
    qml_import = (Path(__file__).resolve().parents[1] / "app" / "qml").as_uri()
    return f"""
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import \"{qml_import}\"

ApplicationWindow {{
    id: root
    width: 520
    height: 260
    visible: true
    property bool expanded: false
    property int radiusSm: 8
    property color textTertiary: "#666666"
    property int typeMeta: 12
    property color textSecondary: "#444444"
    property real letterTight: 0.2
    property int weightMedium: 500
    property int typeLabel: 13
    property bool isDark: false
    property int motionFast: 180
    property int motionPanel: 320
    property int easeStandard: Easing.OutCubic
    property int easeEmphasis: Easing.OutBack

    ColumnLayout {{
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        TextArea {{
            id: editor
            objectName: "editor"
            property bool baoClickAwayEditor: true
            Layout.fillWidth: true
            Layout.preferredHeight: 80
            text: "hello bao"
        }}

        ExpandHeader {{
            id: header
            objectName: "expandHeader"
            Layout.fillWidth: true
            title: "Provider"
            expanded: root.expanded
            onClicked: root.expanded = !root.expanded
        }}
    }}
}}
""".encode("utf-8")


def _build_settings_select_and_mouse_area_window() -> bytes:
    qml_import = (Path(__file__).resolve().parents[1] / "app" / "qml").as_uri()
    return f"""
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import \"{qml_import}\"

ApplicationWindow {{
    id: root
    width: 420
    height: 320
    visible: true
    property bool clicked: false
    property int radiusSm: 8
    property color textTertiary: "#666666"
    property color textSecondary: "#444444"
    property color textPrimary: "#111111"
    property color textPlaceholder: "#777777"
    property color bgInput: "#f2f2f2"
    property color bgInputHover: "#e9e9e9"
    property color bgInputFocus: "#dddddd"
    property color borderSubtle: "#cccccc"
    property color borderFocus: "#ff8800"
    property bool isDark: false
    property int typeLabel: 13
    property int typeButton: 14
    property int typeCaption: 12
    property int typeMeta: 12
    property int weightMedium: 500
    property real letterTight: 0.2
    property int sizeControlHeight: 40
    property int sizeDropdownMaxHeight: 220
    property int sizeOptionHeight: 36
    property int sizeFieldPaddingX: 12
    property int spacingSm: 8
    property int spacingMd: 12
    property int motionUi: 120
    property int motionFast: 120
    property int motionMicro: 80
    property int motionPanel: 180
    property int easeStandard: Easing.OutCubic
    property int easeEmphasis: Easing.OutBack

    SettingsSelect {{
        id: settingsSelect
        objectName: "settingsSelect"
        x: 20
        y: 20
        width: root.width - 40
        label: "Context"
        dotpath: ""
        initialValue: "auto"
        options: [
            {{"label": "auto", "value": "auto"}},
            {{"label": "off", "value": "off"}}
        ]
    }}

    Rectangle {{
        id: hitTarget
        objectName: "hitTarget"
        x: 120
        y: 220
        width: 180
        height: 48
        color: "#cccccc"

        MouseArea {{
            anchors.fill: parent
            onClicked: root.clicked = true
        }}
    }}
}}
""".encode("utf-8")


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
    focus_filter: WindowFocusDismissFilter | None = None

    try:
        editor = root.findChild(QObject, "editor")
        assert editor is not None

        editor.forceActiveFocus()
        _process(30)
        assert bool(editor.property("activeFocus")) is True

        focus_filter = WindowFocusDismissFilter(root)
        _ = focus_filter.eventFilter(root, _mouse_release(10, 10))
        _process(10)

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
    focus_filter: WindowFocusDismissFilter | None = None

    try:
        editor = root.findChild(QObject, "editor")
        assert editor is not None

        editor.forceActiveFocus()
        _process(30)
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
    focus_filter: WindowFocusDismissFilter | None = None

    try:
        editor_a = root.findChild(QObject, "editorA")
        editor_b = root.findChild(QObject, "editorB")
        assert editor_a is not None
        assert editor_b is not None

        focus_filter = _install_focus_filter(root)

        editor_a.forceActiveFocus()
        _process(0)
        assert bool(editor_a.property("activeFocus")) is True
        assert bool(editor_b.property("activeFocus")) is False

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, QPoint(260, 60))
        _process(0)

        assert bool(editor_a.property("activeFocus")) is False
        assert bool(editor_b.property("activeFocus")) is True
    finally:
        _remove_focus_filter(root, focus_filter)
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
    focus_filter: WindowFocusDismissFilter | None = None

    try:
        editor = root.findChild(QObject, "editor")
        button = root.findChild(QObject, "button")
        assert editor is not None
        assert button is not None

        focus_filter = _install_focus_filter(root)

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
        _remove_focus_filter(root, focus_filter)
        root.deleteLater()
        _process(0)


def test_window_focus_dismiss_preserves_single_click_mouse_area_action(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_editor_and_mouse_area_window(), QUrl("inline:EditorAndMouseAreaHarness.qml")
    )
    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()
    focus_filter: WindowFocusDismissFilter | None = None

    try:
        editor = root.findChild(QObject, "editor")
        click_target = root.findChild(QObject, "clickTarget")
        assert editor is not None
        assert click_target is not None

        focus_filter = _install_focus_filter(root)

        editor.forceActiveFocus()
        _process(30)
        assert bool(editor.property("activeFocus")) is True
        assert bool(root.property("clicked")) is False

        QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, QPoint(360, 60))
        _process(30)

        assert bool(editor.property("activeFocus")) is False
        assert bool(root.property("clicked")) is True
    finally:
        _remove_focus_filter(root, focus_filter)
        root.deleteLater()
        _process(0)


def test_window_focus_dismiss_preserves_single_click_expand_header_action(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_editor_and_expand_header_window(),
        QUrl("inline:EditorAndExpandHeaderHarness.qml"),
    )
    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()
    focus_filter: WindowFocusDismissFilter | None = None

    try:
        editor = root.findChild(QObject, "editor")
        header = root.findChild(QObject, "expandHeader")
        assert editor is not None
        assert header is not None

        focus_filter = _install_focus_filter(root)

        editor.forceActiveFocus()
        _process(30)
        assert bool(editor.property("activeFocus")) is True
        assert bool(root.property("expanded")) is False

        header_center = header.mapToScene(
            QPointF(header.property("width") / 2, header.property("height") / 2)
        )
        QTest.mouseClick(
            root,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(int(header_center.x()), int(header_center.y())),
        )
        _process(30)

        assert bool(editor.property("activeFocus")) is False
        assert bool(root.property("expanded")) is True
    finally:
        _remove_focus_filter(root, focus_filter)
        root.deleteLater()
        _process(0)


def test_window_focus_dismiss_closes_settings_select_popup_without_eating_target_click(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_settings_select_and_mouse_area_window(),
        QUrl("inline:SettingsSelectAndMouseAreaHarness.qml"),
    )
    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()
    focus_filter: WindowFocusDismissFilter | None = None

    try:
        settings_select = root.findChild(QObject, "settingsSelect")
        hit_target = root.findChild(QObject, "hitTarget")
        assert settings_select is not None
        assert hit_target is not None
        focus_filter = _install_focus_filter(root)

        select_hit_area = settings_select.findChild(QObject, "settingsSelectHitArea")
        assert select_hit_area is not None

        select_center = select_hit_area.mapToScene(
            QPointF(select_hit_area.property("width") / 2, select_hit_area.property("height") / 2)
        )
        QTest.mouseClick(
            root,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(int(select_center.x()), int(select_center.y())),
        )
        _process(100)

        assert bool(settings_select.property("baoClickAwayPopupOpen")) is True
        assert bool(root.property("clicked")) is False

        hit_center = hit_target.mapToScene(
            QPointF(hit_target.property("width") / 2, hit_target.property("height") / 2)
        )
        QTest.mouseClick(
            root,
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(int(hit_center.x()), int(hit_center.y())),
        )
        _process(100)

        assert bool(settings_select.property("baoClickAwayPopupOpen")) is False
        assert bool(root.property("clicked")) is True
    finally:
        _remove_focus_filter(root, focus_filter)
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
        focus_filter._post_pointer_refresh(root, _mouse_release(10, 10))
        _process(10)
        QCoreApplication.sendPostedEvents(root, QEvent.Type.MouseMove)
        _process(10)

        assert recorder.moves >= 1
    finally:
        if recorder is not None:
            root.removeEventFilter(recorder)
        root.deleteLater()
        _process(0)


def test_refresh_pointer_if_window_active_posts_mouse_move(qapp):
    _ = qapp

    class _FakeApp:
        def applicationState(self):
            return Qt.ApplicationState.ApplicationActive

    class _FakeWindow:
        def isVisible(self):
            return True

    class _FakeFilter:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def _post_pointer_refresh(self, window):
            self.calls.append(window)

    window = _FakeWindow()
    focus_filter = _FakeFilter()

    refresh_pointer_if_window_active(
        cast(QGuiApplication, _FakeApp()),
        cast(QQuickWindow, window),
        cast(WindowFocusDismissFilter, cast(object, focus_filter)),
    )

    assert focus_filter.calls == [window]


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
