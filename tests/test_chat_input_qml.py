from __future__ import annotations

import importlib
from pathlib import Path

from tests.desktop_ui_testkit import process_events as _process
from tests.desktop_ui_testkit import qapp as _shared_qapp
from tests.desktop_ui_testkit import wait_until_ready as _wait_until_ready

pytest = importlib.import_module("pytest")
pytestmark = [pytest.mark.gui, pytest.mark.desktop_ui_smoke]

QtCore = pytest.importorskip("PySide6.QtCore")
QtQml = pytest.importorskip("PySide6.QtQml")
QtTest = pytest.importorskip("PySide6.QtTest")

QObject = QtCore.QObject
QPoint = QtCore.QPoint
QPointF = QtCore.QPointF
QUrl = QtCore.QUrl
Qt = QtCore.Qt
QQmlComponent = QtQml.QQmlComponent
QQmlEngine = QtQml.QQmlEngine
QTest = QtTest.QTest

QML_DIR = Path(__file__).resolve().parents[1] / "app" / "qml"
qapp = _shared_qapp


def _build_composer_window() -> bytes:
    return b"""
import QtQuick 2.15
import QtQuick.Controls 2.15

ApplicationWindow {
    width: 520
    height: 240
    visible: true

    property int sizeFieldPaddingX: 14

    Rectangle {
        anchors.fill: parent
        color: "#202020"

        Rectangle {
            id: composerField
            objectName: "composerField"
            x: 40
            y: 40
            width: 300
            height: 56
            color: "#303030"

            ScrollView {
                id: inputScroll
                objectName: "inputScroll"
                anchors.fill: parent
                clip: true

                TextArea {
                    id: messageInput
                    objectName: "messageInput"
                    background: null
                    wrapMode: TextArea.Wrap
                    leftPadding: sizeFieldPaddingX
                    rightPadding: sizeFieldPaddingX
                    topPadding: 13
                    bottomPadding: 7
                    text: ""
                }
            }
        }
    }
}
"""


def test_chat_composer_click_focus_works_inside_text_input_region(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(_build_composer_window(), QUrl("inline:ChatComposerHarness.qml"))
    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        request_activate = getattr(root, "requestActivate", None)
        if callable(request_activate):
            request_activate()
            _process(30)
        message_input = root.findChild(QObject, "messageInput")
        assert message_input is not None

        message_input_top_left = message_input.mapToScene(QPointF(0, 0))
        click_points = [
            QPoint(int(message_input_top_left.x()) + 24, int(message_input_top_left.y()) + 16),
            QPoint(
                int(message_input_top_left.x()) + int(message_input.property("width")) // 2,
                int(message_input_top_left.y()) + int(message_input.property("height")) // 2,
            ),
            QPoint(
                int(message_input_top_left.x()) + int(message_input.property("width")) - 24,
                int(message_input_top_left.y()) + int(message_input.property("height")) - 16,
            ),
        ]

        for point in click_points:
            QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, point)
            _wait_until_ready(component, timeout_ms=50)
            for _ in range(3):
                if bool(message_input.property("activeFocus")) is True:
                    break
                _process(15)
            assert bool(message_input.property("activeFocus")) is True
            _ = message_input.setProperty("focus", False)
            _process(0)
    finally:
        root.deleteLater()
        _process(0)


def test_chat_view_composer_uses_capped_radius_and_clipping() -> None:
    text = (QML_DIR / "ChatView.qml").read_text(encoding="utf-8")

    assert "readonly property real composerFieldRadius: composerMinHeight / 2" in text
    assert "radius: root.composerFieldRadius" in text
    assert "clip: true" in text
    assert 'objectName: "attachmentStrip"' in text
    assert 'source: "../resources/icons/paperclip.svg"' in text
    assert "event.matches(StandardKey.Paste)" in text
    assert "chatService.pasteClipboardAttachment()" in text
    assert 'GradientStop { position: 1.0; color: "#99000000" }' in text
    assert "border.color: chipHover.containsMouse ? accent : borderSubtle" in text
    assert "add: Transition" in text
    assert 'border.color: root.hasDraftAttachments ? accent : "transparent"' in text


def test_chat_view_reconcile_queue_uses_single_pending_request() -> None:
    text = (QML_DIR / "ChatView.qml").read_text(encoding="utf-8")

    assert "property var pendingPinnedReconcile: null" in text
    assert "reconcileQueued" not in text
    assert "queuedReconcileAnimated" not in text
    assert "pendingPinnedReconcile = { animated: animated !== false }" in text
    assert "var request = messageList.pendingPinnedReconcile" in text
    assert "messageList.pendingPinnedReconcile = null" in text


def test_chat_view_uses_single_deferred_viewport_scheduler() -> None:
    text = (QML_DIR / "ChatView.qml").read_text(encoding="utf-8")

    assert "function scheduleDeferredViewportActions()" in text
    assert "Qt.callLater(flushDeferredViewportActions)" in text
    assert "property bool pendingSessionViewportReady: false" in text
    assert "property var pendingViewportRestore: null" in text
    assert "property bool deferredViewportFlushScheduled: false" in text
