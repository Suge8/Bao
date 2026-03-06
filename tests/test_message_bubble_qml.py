from __future__ import annotations

import importlib
import sys
from pathlib import Path

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QtGui = pytest.importorskip("PySide6.QtGui")
QtQml = pytest.importorskip("PySide6.QtQml")

QEventLoop = QtCore.QEventLoop
QMetaObject = QtCore.QMetaObject
QObject = QtCore.QObject
QTimer = QtCore.QTimer
QUrl = QtCore.QUrl
QGuiApplication = QtGui.QGuiApplication
QQmlComponent = QtQml.QQmlComponent
QQmlEngine = QtQml.QQmlEngine


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


def _build_wrapper(role: str, entrance_style: str, content: str = "收到，杰哥。") -> str:
    qml_dir = (Path(__file__).resolve().parents[1] / "app" / "qml").as_uri()
    return f'''
import QtQuick 2.15
import QtQuick.Controls 2.15
import "{qml_dir}"

Item {{
    width: 420
    height: 160

    property int motionMicro: 120
    property int motionFast: 180
    property int motionUi: 220
    property int motionPanel: 320
    property int motionAmbient: 500
    property int motionBreath: 1100
    property int motionStatusPulse: 600
    property int motionTrackVelocity: 220
    property int easeStandard: Easing.OutCubic
    property int easeEmphasis: Easing.OutBack
    property int easeSoft: Easing.InOutSine
    property int easeLinear: Easing.Linear
    property real motionCopyFlashPeak: 0.42
    property real motionAuraNearPeak: 0.34
    property real motionAuraFarPeak: 0.2
    property real motionGreetingSweepPeak: 0.26
    property real motionTypingPulseMinOpacity: 0.28
    property int motionEnterOffsetY: 10
    property color statusError: "#F05A5A"
    property color accent: "#FFA11A"
    property color accentGlow: "#88FFF5DF"
    property color accentMuted: "#22FFA11A"
    property color accentHover: "#FFB444"
    property color borderSubtle: "#30FFFFFF"
    property color textPrimary: "#FFF6EA"
    property color textSecondary: "#C8B09A"
    property color bgCard: "#1A120D"
    property color bgCardHover: "#23170F"
    property int sizeBubbleRadius: 18
    property int sizeSystemBubbleRadius: 11
    property int typeBody: 15
    property int typeMeta: 12
    property real lineHeightBody: 1.4
    property real letterTight: 0.2
    property int weightMedium: Font.Medium
    property color chatSystemAuraFar: "#46FFA11A"
    property color chatSystemAuraNear: "#36FFA11A"
    property color chatSystemAuraErrorFar: "#2EF05A5A"
    property color chatSystemAuraErrorNear: "#44F05A5A"
    property color chatSystemBubbleBg: "#28FFB33D"
    property color chatSystemBubbleBorder: "#58FFCB7A"
    property color chatSystemBubbleErrorBg: "#20F05A5A"
    property color chatSystemBubbleErrorBorder: "#58F05A5A"
    property color chatSystemBubbleOverlay: "#22FFA11A"
    property color chatSystemBubbleErrorOverlay: "#08F05A5A"
    property color chatSystemText: "#F6DEBA"
    property color chatGreetingAuraFar: "#22FFD6A1"
    property color chatGreetingAuraNear: "#34FFE7C2"
    property color chatGreetingBubbleBgStart: "#FF2B2118"
    property color chatGreetingBubbleBgEnd: "#FF201812"
    property color chatGreetingBubbleBorder: "#50FFD19A"
    property color chatGreetingBubbleOverlay: "#10FFFFFF"
    property color chatGreetingBubbleHighlight: "#88FFF5DF"
    property color chatGreetingSweep: "#16FFFFFF"
    property color chatGreetingAccent: "#F6C889"
    property color chatGreetingText: "#FFF6EA"
    property color chatBubbleCopyFlashUser: "#40FFFFFF"
    property color chatBubbleErrorTint: "#15F05A5A"

    MessageBubble {{
        id: bubble
        objectName: "bubble"
        anchors.fill: parent
        role: "{role}"
        content: "{content}"
        format: "plain"
        status: "done"
        entranceStyle: "{entrance_style}"
        entrancePending: false
        entranceConsumed: true
        toastFunc: function() {{}}
    }}
}}
'''


@pytest.mark.parametrize(
    ("role", "entrance_style", "flash_name", "ripple_name", "sheen_name"),
    [
        ("assistant", "none", "copyFlash", "copyRipple", "copySheen"),
        ("system", "none", "systemCopyFlash", "systemCopyRipple", "systemCopySheen"),
        ("system", "greeting", "systemCopyFlash", "systemCopyRipple", "systemCopySheen"),
    ],
)
def test_message_click_feedback_restored(
    qapp,
    role: str,
    entrance_style: str,
    flash_name: str,
    ripple_name: str,
    sheen_name: str,
):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper(role, entrance_style).encode("utf-8"),
        QUrl("inline:MessageBubbleHarness.qml"),
    )

    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        bubble = root.findChild(QObject, "bubble")
        flash = root.findChild(QObject, flash_name)
        ripple = root.findChild(QObject, ripple_name)
        sheen = root.findChild(QObject, sheen_name)

        assert bubble is not None
        assert flash is not None
        assert ripple is not None
        assert sheen is not None

        start_progress = float(sheen.property("progress"))
        ok = QMetaObject.invokeMethod(bubble, "copyCurrentMessage")
        assert ok

        _process(60)

        assert float(flash.property("opacity")) > 0.0
        assert float(ripple.property("opacity")) > 0.0
        assert float(ripple.property("scale")) > 0.92
        assert float(sheen.property("opacity")) > 0.0
        assert float(sheen.property("progress")) > start_progress
    finally:
        root.deleteLater()
        _process(0)


@pytest.mark.parametrize(
    ("role", "entrance_style"),
    [("system", "none"), ("system", "greeting")],
)
def test_system_aura_near_stays_within_bubble_width(qapp, role: str, entrance_style: str):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper(role, entrance_style).encode("utf-8"),
        QUrl("inline:MessageBubbleHarness.qml"),
    )

    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        aura = root.findChild(QObject, "systemAuraNear")
        bubble = root.findChild(QObject, "systemBubble")

        assert aura is not None
        assert bubble is not None
        assert float(aura.property("width")) == float(bubble.property("width"))
        assert float(aura.property("x")) == float(bubble.property("x"))
    finally:
        root.deleteLater()
        _process(0)


def test_tall_assistant_copy_sheen_uses_centered_band(qapp):
    content = "在这儿待命，\n你下一句要我接什么我就接什么，\n我会继续在这里。"
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper("assistant", "none", content).encode("utf-8"),
        QUrl("inline:MessageBubbleHarness.qml"),
    )

    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        bubble = root.findChild(QObject, "bubble")
        bubble_body = root.findChild(QObject, "bubbleBody")
        sheen = root.findChild(QObject, "copySheen")

        assert bubble is not None
        assert bubble_body is not None
        assert sheen is not None

        ok = QMetaObject.invokeMethod(bubble, "copyCurrentMessage")
        assert ok

        _process(60)

        bubble_height = float(bubble_body.property("height"))
        sheen_height = float(sheen.property("height"))
        sheen_y = float(sheen.property("y"))

        assert bubble_height > 60.0
        assert abs(sheen_height - bubble_height) < 1.0
        assert abs(sheen_y) < 1.0
    finally:
        root.deleteLater()
        _process(0)


def test_copy_feedback_restarts_from_baseline_on_second_click(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper("assistant", "none").encode("utf-8"),
        QUrl("inline:MessageBubbleHarness.qml"),
    )

    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        bubble = root.findChild(QObject, "bubble")
        sheen = root.findChild(QObject, "copySheen")

        assert bubble is not None
        assert sheen is not None

        assert QMetaObject.invokeMethod(bubble, "copyCurrentMessage")
        _process(60)
        first_progress = float(sheen.property("progress"))

        assert QMetaObject.invokeMethod(bubble, "copyCurrentMessage")
        _process(10)

        assert float(sheen.property("progress")) < first_progress
    finally:
        root.deleteLater()
        _process(0)
