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


def _build_wrapper(
    role: str,
    entrance_style: str,
    content: str = "收到，杰哥。",
    *,
    dark: bool = True,
    status: str = "done",
    entrance_pending: bool = False,
    show_date_divider: bool = False,
    date_divider_text: str = "",
    attachments_qml: str = "[]",
    references_qml: str = "({})",
) -> str:
    qml_dir = (Path(__file__).resolve().parents[1] / "app" / "qml").as_uri()
    greeting_aura_far = "#22FFD6A1" if dark else "#0EE0BE93"
    greeting_aura_near = "#34FFE7C2" if dark else "#18E8C79F"
    greeting_bubble_bg_start = "#FF2B2118" if dark else "#FFF7F3EC"
    greeting_bubble_bg_end = "#FF201812" if dark else "#FFF7F3EC"
    greeting_bubble_border = "#50FFD19A" if dark else "#1F8F6A47"
    greeting_bubble_overlay = "#10FFFFFF" if dark else "#06FFFFFF"
    greeting_bubble_highlight = "#88FFF5DF" if dark else "#42FFFFFF"
    greeting_sweep = "#16FFFFFF" if dark else "#10FFFFFF"
    greeting_accent = "#F6C889" if dark else "#A8641F"
    greeting_text = "#FFF6EA" if dark else "#402715"
    greeting_icon_source = (
        "../resources/icons/ignite-dark.svg" if dark else "../resources/icons/ignite-light.svg"
    )
    return f'''
import QtQuick 2.15
import QtQuick.Controls 2.15
import "{qml_dir}"

Item {{
    width: 420
    height: 220

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
    property color chatGreetingAuraFar: "{greeting_aura_far}"
    property color chatGreetingAuraNear: "{greeting_aura_near}"
    property color chatGreetingBubbleBgStart: "{greeting_bubble_bg_start}"
    property color chatGreetingBubbleBgEnd: "{greeting_bubble_bg_end}"
    property color chatGreetingBubbleBorder: "{greeting_bubble_border}"
    property color chatGreetingBubbleOverlay: "{greeting_bubble_overlay}"
    property color chatGreetingBubbleHighlight: "{greeting_bubble_highlight}"
    property color chatGreetingSweep: "{greeting_sweep}"
    property color chatGreetingAccent: "{greeting_accent}"
    property color chatGreetingText: "{greeting_text}"
    property string chatGreetingIconSource: "{greeting_icon_source}"
    property color chatBubbleCopyFlashUser: "#40FFFFFF"
    property color chatBubbleErrorTint: "#15F05A5A"

    MessageBubble {{
        id: bubble
        objectName: "bubble"
        anchors.fill: parent
        role: "{role}"
        content: "{content}"
        format: "plain"
        status: "{status}"
        attachments: {attachments_qml}
        references: {references_qml}
        entranceStyle: "{entrance_style}"
        entrancePending: {str(entrance_pending).lower()}
        showDateDivider: {str(show_date_divider).lower()}
        dateDividerText: "{date_divider_text}"
        toastFunc: function() {{}}
    }}
}}
'''


@pytest.mark.parametrize(
    ("role", "entrance_style", "flash_name", "ripple_name", "sheen_name"),
    [
        ("assistant", "none", "copyFlash", "copyRipple", "copySheen"),
        ("assistant", "greeting", "systemCopyFlash", "systemCopyRipple", "systemCopySheen"),
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


def test_message_bubble_shows_attachment_strip(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper(
            "assistant",
            "none",
            content="这里有附件",
            attachments_qml='[{fileName: "image.png", fileSizeLabel: "12 KB", filePath: "/tmp/image.png", previewUrl: "file:///tmp/image.png", isImage: true, extensionLabel: "PNG"}]',
        ).encode("utf-8"),
        QUrl("inline:MessageBubbleAttachmentHarness.qml"),
    )

    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        strip = root.findChild(QObject, "attachmentStrip")
        assert strip is not None
        assert bool(strip.property("visible")) is True
        assert float(strip.property("width")) > 0
    finally:
        root.deleteLater()
        _process(0)


def test_message_bubble_shows_memory_reference_summary(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper(
            "assistant",
            "none",
            content="整理好了",
            references_qml='({longTermCategories: ["project"], relatedMemoryCount: 2, experienceCount: 1})',
        ).encode("utf-8"),
        QUrl("inline:MessageBubbleReferenceHarness.qml"),
    )

    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        reference_text = root.findChild(QObject, "referenceText")
        assert reference_text is not None
        assert bool(reference_text.property("visible")) is True
        assert "2" in str(reference_text.property("text"))
        assert "1" in str(reference_text.property("text"))
    finally:
        root.deleteLater()
        _process(0)


@pytest.mark.parametrize(
    ("role", "entrance_style"),
    [("system", "none"), ("system", "greeting"), ("assistant", "greeting")],
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


def test_date_divider_renders_above_bubble(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper(
            "assistant",
            "none",
            "新的时间段。",
            show_date_divider=True,
            date_divider_text="3/7",
        ).encode("utf-8"),
        QUrl("inline:MessageBubbleHarness.qml"),
    )

    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        divider = root.findChild(QObject, "dateDivider")
        divider_text = root.findChild(QObject, "dateDividerText")
        bubble_body = root.findChild(QObject, "bubbleBody")

        assert divider is not None
        assert divider_text is not None
        assert bubble_body is not None
        assert bool(divider.property("visible")) is True
        assert str(divider_text.property("text")) == "3/7"
        assert float(bubble_body.property("y")) >= float(divider.property("height"))
    finally:
        root.deleteLater()
        _process(0)


@pytest.mark.parametrize(
    ("dark", "expected_icon"),
    [(True, "ignite-dark.svg"), (False, "ignite-light.svg")],
)
def test_greeting_icon_uses_theme_specific_asset(qapp, dark: bool, expected_icon: str):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper("assistant", "greeting", dark=dark).encode("utf-8"),
        QUrl("inline:MessageBubbleGreetingIconHarness.qml"),
    )

    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        icon = root.findChild(QObject, "greetingIcon")

        assert icon is not None
        assert expected_icon in str(icon.property("source"))
    finally:
        root.deleteLater()
        _process(0)


def test_light_greeting_uses_flat_bubble_and_compact_height(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper("assistant", "greeting", dark=False).encode("utf-8"),
        QUrl("inline:MessageBubbleGreetingLightHarness.qml"),
    )

    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        bubble = root.findChild(QObject, "systemBubble")
        gradient = root.findChild(QObject, "greetingGradient")
        sweep = root.findChild(QObject, "greetingSweep")

        assert bubble is not None
        assert gradient is not None
        assert sweep is not None
        assert bool(gradient.property("visible")) is False
        assert bool(sweep.property("visible")) is False
        assert float(bubble.property("height")) <= 44.0
    finally:
        root.deleteLater()
        _process(0)


def test_typing_indicator_morphs_into_content_in_same_bubble(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper(
            "assistant",
            "assistantReceived",
            "",
            status="typing",
        ).encode("utf-8"),
        QUrl("inline:MessageBubbleTypingMorphHarness.qml"),
    )

    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        bubble = root.findChild(QObject, "bubble")
        typing = root.findChild(QObject, "typingIndicator")
        content = root.findChild(QObject, "contentText")

        assert bubble is not None
        assert typing is not None
        assert content is not None
        assert float(typing.property("opacity")) > 0.98
        assert float(content.property("opacity")) < 0.02

        bubble.setProperty("content", "Bao 在这。")
        bubble.setProperty("status", "done")

        _process(40)

        assert 0.0 < float(typing.property("opacity")) < 1.0
        assert 0.0 < float(content.property("opacity")) < 1.0
        assert float(content.property("scale")) < 1.0

        _process(320)

        assert float(typing.property("opacity")) < 0.02
        assert float(content.property("opacity")) > 0.98
        assert abs(float(content.property("scale")) - 1.0) < 0.01
    finally:
        root.deleteLater()
        _process(0)


def test_pending_surface_settles_when_user_message_finishes(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper(
            "user",
            "userSent",
            "我已经发出去了。",
            status="pending",
        ).encode("utf-8"),
        QUrl("inline:MessageBubblePendingFinalizeHarness.qml"),
    )

    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        bubble = root.findChild(QObject, "bubble")
        overlay = root.findChild(QObject, "pendingOverlay")

        assert bubble is not None
        assert overlay is not None
        assert float(overlay.property("opacity")) > 0.98
        assert float(overlay.property("scale")) > 1.0

        bubble.setProperty("status", "done")
        _process(60)

        assert 0.0 < float(overlay.property("opacity")) < 1.0
        assert 1.0 < float(overlay.property("scale")) < 1.017

        _process(360)

        assert float(overlay.property("opacity")) < 0.02
        assert abs(float(overlay.property("scale")) - 1.0) < 0.01
    finally:
        root.deleteLater()
        _process(0)


@pytest.mark.parametrize(
    ("role", "entrance_style", "expected_sign"),
    [
        ("user", "userSent", 1),
        ("assistant", "assistantReceived", -1),
    ],
)
def test_message_entrance_animation_has_directional_shift(
    qapp, role: str, entrance_style: str, expected_sign: int
):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper(
            role,
            entrance_style,
            entrance_pending=True,
        ).encode("utf-8"),
        QUrl("inline:MessageBubbleEntranceHarness.qml"),
    )

    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        bubble = root.findChild(QObject, "bubbleBody")
        shift = root.findChild(QObject, "bubbleEntranceShift")
        glow = root.findChild(QObject, "bubbleEntranceGlow")

        assert bubble is not None
        assert shift is not None
        assert glow is not None

        assert float(bubble.property("opacity")) == 0.0

        _process(40)

        shift_x = float(shift.property("x"))
        assert shift_x * expected_sign > 0.0
        assert float(glow.property("opacity")) > 0.0

        _process(420)

        assert abs(float(shift.property("x"))) < 0.6
        assert abs(float(shift.property("y"))) < 0.6
        assert float(bubble.property("opacity")) > 0.98
    finally:
        root.deleteLater()
        _process(0)
