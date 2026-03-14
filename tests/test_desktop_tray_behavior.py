from __future__ import annotations

import importlib
import sys

pytest = importlib.import_module("pytest")

QtCore = pytest.importorskip("PySide6.QtCore")
QtGui = pytest.importorskip("PySide6.QtGui")
QtQuick = pytest.importorskip("PySide6.QtQuick")

QEventLoop = QtCore.QEventLoop
QGuiApplication = QtGui.QGuiApplication
QCloseEvent = QtGui.QCloseEvent
QTimer = QtCore.QTimer
QQuickWindow = QtQuick.QQuickWindow


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    yield app


def _process(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_resolve_tray_icon_prefers_transparent_logo_bun():
    from app.main import resolve_tray_icon_path

    path = resolve_tray_icon_path()

    assert path is not None
    assert path.name == "logo-bun.png"


def test_build_monochrome_tray_icon_scales_logo_and_tints_by_theme():
    from app.main import build_monochrome_tray_icon, resolve_tray_icon_path

    path = resolve_tray_icon_path()
    assert path is not None

    light_icon = build_monochrome_tray_icon(path, dark_mode=False)
    dark_icon = build_monochrome_tray_icon(path, dark_mode=True)

    assert light_icon is not None
    assert dark_icon is not None

    light_image = light_icon.pixmap(32, 32).toImage()
    dark_image = dark_icon.pixmap(32, 32).toImage()
    scale = max(1, light_image.width() // 32)

    def sample(image, x: int, y: int):
        return image.pixelColor(x * scale, y * scale)

    light_center = sample(light_image, 16, 16)
    dark_center = sample(dark_image, 16, 16)

    assert light_center.alpha() > 0
    assert dark_center.alpha() > 0
    assert light_center.red() < 40
    assert dark_center.red() > 220

    top_left = sample(light_image, 0, 0)
    assert top_left.alpha() == 0
    assert sample(light_image, 16, 9).alpha() > 0
    assert sample(light_image, 16, 16).alpha() > 0
    assert sample(light_image, 10, 17).alpha() == 0


def test_hide_on_close_filter_hides_window_when_enabled(qt_app):
    _ = qt_app
    from app.main import HideOnCloseEventFilter

    window = QQuickWindow()
    hidden: list[bool] = []
    filter_obj = HideOnCloseEventFilter(
        window,
        should_hide_on_close=lambda: True,
        on_hide_requested=lambda: (hidden.append(True), window.hide()),
    )
    window.installEventFilter(filter_obj)
    window.show()
    _process(0)

    event = QCloseEvent()
    handled = filter_obj.eventFilter(window, event)

    assert handled is True
    assert hidden == [True]
    assert event.isAccepted() is False
    assert window.isVisible() is False


def test_hide_on_close_filter_allows_real_close_when_disabled(qt_app):
    _ = qt_app
    from app.main import HideOnCloseEventFilter

    window = QQuickWindow()
    hidden: list[bool] = []
    filter_obj = HideOnCloseEventFilter(
        window,
        should_hide_on_close=lambda: False,
        on_hide_requested=lambda: hidden.append(True),
    )

    event = QCloseEvent()
    handled = filter_obj.eventFilter(window, event)

    assert handled is False
    assert hidden == []
    assert event.isAccepted() is True
