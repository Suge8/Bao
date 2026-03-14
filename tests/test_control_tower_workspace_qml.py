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

QEventLoop = QtCore.QEventLoop
QPoint = QtCore.QPoint
QPointF = QtCore.QPointF
Qt = QtCore.Qt
QTimer = QtCore.QTimer
QUrl = QtCore.QUrl
QGuiApplication = QtGui.QGuiApplication
QQmlComponent = QtQml.QQmlComponent
QQmlEngine = QtQml.QQmlEngine
QQuickItem = QtQuick.QQuickItem
QQuickView = QtQuick.QQuickView
QTest = QtTest.QTest


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


def _build_wrapper(*, selected_profile_qml: str, expected_title: str) -> str:
    qml_dir = (Path(__file__).resolve().parents[1] / "app" / "qml").as_uri()
    return f'''
import QtQuick 2.15
import QtQuick.Controls 2.15
import "{qml_dir}"

Item {{
    width: 1400
    height: 920

    property bool isDark: true
    property string effectiveLang: "zh"
    property string uiLanguage: "zh"
    property color accent: "#FFA11A"
    property color accentHover: "#FFB444"
    property color accentGlow: "#66FFA11A"
    property color borderSubtle: "#30FFFFFF"
    property color textPrimary: "#FFF6EA"
    property color textSecondary: "#C8B09A"
    property color textTertiary: "#9D8778"
    property color bgCard: "#1A120D"
    property color bgCardHover: "#23170F"
    property color statusSuccess: "#52D68A"
    property color statusError: "#F05A5A"
    property int typeTitle: 22
    property int typeBody: 16
    property int typeLabel: 14
    property int typeCaption: 11
    property int typeMeta: 12
    property int weightBold: Font.Bold
    property int weightDemiBold: Font.DemiBold
    property int weightMedium: Font.Medium
    property real motionHoverScaleSubtle: 1.0
    property int motionFast: 180
    property int motionUi: 220
    property int motionBreath: 1100
    property int easeStandard: Easing.OutCubic
    property int easeEmphasis: Easing.OutBack
    property int easeSoft: Easing.InOutSine

    QtObject {{
        id: supervisor
        objectName: "supervisorHarness"
        property int selectCalls: 0
        property int activateCalls: 0
        property var overview: ({{
            title: "指挥舱",
            liveProfileId: "default",
            profileCount: 2
        }})
        property var profiles: [
            {{
                id: "default",
                displayName: "日常",
                avatarSource: "",
                statusSummary: "2 个会话 / 1 个子代理工作中",
                updatedLabel: "刚刚",
                totalSessionCount: 2,
                totalChildSessionCount: 1,
                workingCount: 2,
                automationCount: 2,
                attentionCount: 0,
                isGatewayLive: true,
                channelKeys: ["desktop", "telegram"]
            }},
            {{
                id: "work",
                displayName: "Work",
                avatarSource: "",
                statusSummary: "1 个自动化待命",
                updatedLabel: "3 分钟前",
                totalSessionCount: 3,
                totalChildSessionCount: 0,
                workingCount: 0,
                automationCount: 1,
                attentionCount: 1,
                isGatewayLive: false,
                channelKeys: ["telegram"]
            }}
        ]
        property var workingItems: [
            {{
                id: "default:session",
                profileId: "default",
                title: "Main Thread",
                summary: "回复中",
                updatedLabel: "刚刚",
                isLive: true,
                canOpen: true,
                avatarSource: "",
                personaVariant: "primary",
                accentKey: "desktop",
                glyphSource: "",
                statusKey: "running",
                statusLabel: "运行中"
            }}
        ]
        property var completedItems: [
            {{
                id: "default:start",
                profileId: "default",
                title: "AI 问候",
                summary: "刚发送完问候",
                updatedLabel: "刚刚",
                isLive: true,
                canOpen: true,
                avatarSource: "",
                personaVariant: "primary",
                accentKey: "desktop",
                glyphSource: "",
                statusKey: "completed",
                statusLabel: "已完成"
            }}
        ]
        property var automationItems: [
            {{
                id: "default:cron",
                profileId: "default",
                title: "Daily Review",
                summary: "每 30 分钟",
                updatedLabel: "2 小时后",
                isLive: true,
                canOpen: true,
                avatarSource: "",
                personaVariant: "automation",
                accentKey: "cron",
                glyphSource: "",
                statusKey: "scheduled",
                statusLabel: "已调度"
            }}
        ]
        property var attentionItems: [
            {{
                id: "work:issue",
                profileId: "work",
                title: "自动检查",
                summary: "缺少检查说明",
                updatedLabel: "3 分钟前",
                isLive: false,
                canOpen: false,
                avatarSource: "",
                personaVariant: "automation",
                accentKey: "heartbeat",
                glyphSource: "",
                statusKey: "error",
                statusLabel: "待处理"
            }}
        ]
        property var selectedProfile: {selected_profile_qml}
        function refresh() {{}}
        function selectProfile(_profileId) {{ selectCalls += 1 }}
        function activateProfile(_profileId) {{ activateCalls += 1 }}
        function selectItem(_itemId) {{}}
        function openSelectedTarget() {{}}
    }}

    ControlTowerWorkspace {{
        id: workspace
        anchors.fill: parent
        active: true
        supervisorService: supervisor
    }}
}}
'''


def _build_segmented_tabs_wrapper() -> str:
    qml_dir = (Path(__file__).resolve().parents[1] / "app" / "qml").as_uri()
    return f'''
import QtQuick 2.15
import QtQuick.Controls 2.15
import "{qml_dir}"

Item {{
    width: 360
    height: 120

    property bool isDark: false
    property color accent: "#FFA11A"
    property color borderSubtle: "#14000000"
    property color textSecondary: "#6F5A4B"
    property int typeLabel: 14
    property int motionFast: 180
    property int easeStandard: Easing.OutCubic
    property int easeEmphasis: Easing.OutBack

    SegmentedTabs {{
        anchors.centerIn: parent
        currentValue: "installed"
        items: [
            {{ value: "installed", label: "已安装", icon: "../resources/icons/vendor/iconoir/book-stack.svg" }},
            {{ value: "discover", label: "发现", icon: "../resources/icons/vendor/iconoir/page-search.svg" }}
        ]
    }}
}}
'''


@pytest.mark.parametrize(
    ("selected_profile_qml", "expected_title"),
    [
        ("({})", "指挥舱"),
        (
            '({id: "default", displayName: "日常", totalSessionCount: 2, totalChildSessionCount: 1, isGatewayLive: true})',
            "指挥舱",
        ),
    ],
)
def test_control_tower_workspace_loads_scope_title(
    qapp,
    selected_profile_qml: str,
    expected_title: str,
):
    _ = qapp
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper(
            selected_profile_qml=selected_profile_qml,
            expected_title=expected_title,
        ).encode("utf-8"),
        QUrl("inline:ControlTowerWorkspaceHarness.qml"),
    )

    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        title = root.findChild(QtCore.QObject, "controlTowerScopeTitle")
        assert title is not None
        assert str(title.property("text")) == expected_title
    finally:
        root.deleteLater()
        _process(0)


def test_control_tower_profile_button_click_does_not_select_card(qapp, tmp_path: Path):
    _ = qapp
    qml_path = tmp_path / "ControlTowerWorkspaceClickHarness.qml"
    qml_path.write_text(
        _build_wrapper(
            selected_profile_qml="({})",
            expected_title="指挥舱",
        ),
        encoding="utf-8",
    )

    view = QQuickView()
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    view.setColor(QtGui.QColor("#FFFDF9"))
    view.setSource(QUrl.fromLocalFile(str(qml_path)))
    assert view.status() == QQuickView.Ready, view.errors()
    view.show()
    _process(100)

    root = view.rootObject()
    assert root is not None

    supervisor = root.findChild(QtCore.QObject, "supervisorHarness")
    assert supervisor is not None
    button = None
    queue = [root] if isinstance(root, QQuickItem) else []
    while queue and button is None:
        current = queue.pop(0)
        if str(current.property("text") or "") == "切换":
            button = current
            break
        queue.extend(current.childItems())
    assert isinstance(button, QQuickItem)

    center = button.mapToScene(QPointF(button.width() / 2.0, button.height() / 2.0)).toPoint()
    QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, QPoint(center.x(), center.y()))
    _process(50)

    assert int(supervisor.property("activateCalls")) == 1
    assert int(supervisor.property("selectCalls")) == 0

    view.close()


def test_segmented_tabs_render_selected_highlight_on_first_paint(qapp):
    _ = qapp
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_segmented_tabs_wrapper().encode("utf-8"),
        QUrl("inline:SegmentedTabsHarness.qml"),
    )

    _wait_until_ready(component)

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        _process(50)
        highlight = root.findChild(QtCore.QObject, "segmentedTabsHighlight")
        assert highlight is not None
        assert float(highlight.property("width")) > 0
        assert float(highlight.property("height")) > 0
    finally:
        root.deleteLater()
        _process(0)
