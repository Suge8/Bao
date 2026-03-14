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


def _build_wrapper() -> str:
    qml_dir = (Path(__file__).resolve().parents[1] / "app" / "qml").as_uri()
    return f'''
import QtQuick 2.15
import "{qml_dir}"

Item {{
    width: 32
    height: 32
    property int observedFillMode: icon.fillMode

    AppIcon {{
        id: icon
        objectName: "appIcon"
        anchors.centerIn: parent
        width: 18
        height: 18
        source: "../app/resources/icons/sidebar-tools.svg"
        sourceSize: Qt.size(18, 18)
    }}
}}
'''


def test_app_icon_uses_ui_icon_defaults(qapp):
    _ = qapp
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        _build_wrapper().encode("utf-8"),
        QUrl("inline:AppIconHarness.qml"),
    )

    deadline = 20
    while component.status() == QQmlComponent.Loading and deadline > 0:
        _process(25)
        deadline -= 1

    assert component.status() == QQmlComponent.Ready, component.errors()
    root = component.create()
    assert root is not None, component.errors()

    try:
        icon = next(
            obj for obj in root.findChildren(QtCore.QObject) if obj.objectName() == "appIcon"
        )
        assert bool(icon.property("smooth")) is True
        assert bool(icon.property("mipmap")) is False
        assert int(root.property("observedFillMode")) == 1
    finally:
        root.deleteLater()
        _process(0)
