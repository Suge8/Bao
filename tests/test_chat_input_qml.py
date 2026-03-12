from __future__ import annotations

import importlib
import sys
from pathlib import Path

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QtGui = pytest.importorskip("PySide6.QtGui")
QtQml = pytest.importorskip("PySide6.QtQml")
QtTest = pytest.importorskip("PySide6.QtTest")

QEventLoop = QtCore.QEventLoop
QObject = QtCore.QObject
QPoint = QtCore.QPoint
QTimer = QtCore.QTimer
QUrl = QtCore.QUrl
Qt = QtCore.Qt
QGuiApplication = QtGui.QGuiApplication
QQmlComponent = QtQml.QQmlComponent
QQmlEngine = QtQml.QQmlEngine
QTest = QtTest.QTest

QML_DIR = Path(__file__).resolve().parents[1] / "app" / "qml"


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


def test_chat_composer_click_target_covers_full_field(qapp):
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
        composer = root.findChild(QObject, "composerField")
        message_input = root.findChild(QObject, "messageInput")
        assert composer is not None
        assert message_input is not None

        click_points = [
            QPoint(45, 45),
            QPoint(55, 60),
            QPoint(180, 68),
            QPoint(330, 90),
        ]

        for point in click_points:
            QTest.mouseClick(root, Qt.LeftButton, Qt.NoModifier, point)
            _process(0)
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
