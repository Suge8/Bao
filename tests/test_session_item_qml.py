from __future__ import annotations

import importlib
import sys
from pathlib import Path

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QtGui = pytest.importorskip("PySide6.QtGui")
QtQml = pytest.importorskip("PySide6.QtQml")

QEventLoop = QtCore.QEventLoop
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


def _build_wrapper(relative_time: str, *, dark: bool = True) -> str:
    qml_dir = (Path(__file__).resolve().parents[1] / "app" / "qml").as_uri()
    return f'''
import QtQuick 2.15
import QtQuick.Controls 2.15
import "{qml_dir}"

Item {{
    width: 320
    height: 52

    property int sizeSessionRow: 44
    property real motionSelectionScaleActive: 1.0
    property real motionSelectionScaleHover: 1.0
    property real motionHoverScaleSubtle: 1.0
    property real motionDeleteHiddenScale: 0.92
    property int motionMicro: 120
    property int motionFast: 180
    property int motionUi: 220
    property int easeStandard: Easing.OutCubic
    property int easeEmphasis: Easing.OutBack
    property color sessionRowActiveBg: "#22FFFFFF"
    property color sessionRowHoverBg: "#18FFFFFF"
    property color sessionRowIdleBg: "#00000000"
    property color sessionRowActiveBorder: "#55FFFFFF"
    property color sessionRowHoverBorder: "#33FFFFFF"
    property color sessionRowIdleBorder: "#00000000"
    property real opacityDimmedActive: 0.78
    property real opacityDimmedIdle: 0.58
    property color textPrimary: "#FFF6EA"
    property color textSecondary: "#C8B09A"
    property color textTertiary: "#9D8778"
    property int typeLabel: 14
    property int typeMeta: 11
    property int weightDemiBold: Font.DemiBold
    property int weightMedium: Font.Medium
    property color sessionDeleteHoverBg: "#30FFFFFF"
    property color sessionDeleteIdleBg: "#00000000"
    property color sessionDeleteHoverBorder: "#00000000"
    property color sessionDeleteIdleBorder: "#00000000"
    property color sessionUnreadDot: "#FFA11A"
    property bool isDark: {str(dark).lower()}

    SessionItem {{
        id: item
        anchors.fill: parent
        sessionKey: "desktop:local::notes"
        sessionTitle: "notes"
        sessionRelativeTime: "{relative_time}"
    }}
}}
'''


def test_session_item_renders_relative_time_label(qapp):
    _ = qapp
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper("2h").encode("utf-8"),
        QUrl("inline:SessionItemHarness.qml"),
    )

    deadline = 20
    while component.status() == QQmlComponent.Loading and deadline > 0:
        _process(25)
        deadline -= 1

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        time_label = next(
            obj
            for obj in root.findChildren(QtCore.QObject)
            if obj.objectName() == "sessionRelativeTime"
        )
        assert str(time_label.property("text")) == "2h"
        assert bool(time_label.property("visible")) is True
    finally:
        root.deleteLater()
        _process(0)


@pytest.mark.parametrize(
    ("dark", "expected_icon"),
    [(True, "sidebar-close.svg"), (False, "sidebar-close-light.svg")],
)
def test_session_item_delete_icon_tracks_theme(qapp, dark: bool, expected_icon: str):
    _ = qapp
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper("2h", dark=dark).encode("utf-8"),
        QUrl("inline:SessionItemThemeHarness.qml"),
    )

    deadline = 20
    while component.status() == QQmlComponent.Loading and deadline > 0:
        _process(25)
        deadline -= 1

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        delete_icon = next(
            obj
            for obj in root.findChildren(QtCore.QObject)
            if obj.objectName() == "sessionDeleteIcon"
        )
        assert expected_icon in str(delete_icon.property("source"))
    finally:
        root.deleteLater()
        _process(0)
