from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, cast

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QLocale,
    QObject,
    QPointF,
    QRectF,
    QResource,
    Qt,
    QTimer,
    QUrl,
    Slot,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QIcon,
    QImage,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QSurfaceFormat,
)
from PySide6.QtQml import QQmlApplicationEngine, QQmlProperty
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from typing_extensions import override

BUNDLED_APP_FONT_FILENAME = "OPPO Sans.ttf"
BUNDLED_APP_FONT_FAMILY_PREFIX = ""
BUNDLED_APP_FONT_RELATIVE_PATHS = (
    f"app/resources/fonts/{BUNDLED_APP_FONT_FILENAME}",
    f"resources/fonts/{BUNDLED_APP_FONT_FILENAME}",
)
PREFERRED_SYSTEM_FONT_FAMILIES = (
    "Helvetica Neue",
    ".AppleSystemUIFont",
    "Segoe UI",
    "Arial",
    "Noto Sans",
    "DejaVu Sans",
)
WINDOWS_APP_ICON_RELATIVE_PATHS = (
    "resources/logo.ico",
    "app/resources/logo.ico",
)
WINDOWS_APP_ICON_FALLBACK_RELATIVE_PATHS = (
    "resources/logo-circle.png",
    "app/resources/logo-circle.png",
    "assets/logo.ico",
    "assets/logo.jpg",
    "assets/logo.jpeg",
    "assets/logo.png",
)
DEFAULT_APP_ICON_RELATIVE_PATHS = (
    "assets/logo.jpg",
    "assets/logo.jpeg",
    "assets/logo.png",
    "assets/logo.ico",
)
TRAY_APP_ICON_RELATIVE_PATHS = (
    "resources/logo-bun.png",
    "app/resources/logo-bun.png",
    "resources/logo-bun-light.png",
    "app/resources/logo-bun-light.png",
    "resources/logo-bun-dark.png",
    "app/resources/logo-bun-dark.png",
)
QML_RESOURCE_MAIN_URL = "qrc:/app/qml/Main.qml"
QML_RCC_RELATIVE_PATHS = (
    "app/resources/desktop_qml.rcc",
    "resources/desktop_qml.rcc",
    "desktop_qml.rcc",
)
_REGISTERED_QML_BUNDLE: str | None = None


_CLICK_AWAY_EDITOR_PROP = "baoClickAwayEditor"


def _iter_object_ancestors(obj: QObject | None):
    seen: set[int] = set()
    current = obj
    while current is not None:
        identity = id(current)
        if identity in seen:
            return
        seen.add(identity)
        yield current

        parent_item = getattr(current, "parentItem", None)
        if callable(parent_item):
            item_owner = parent_item()
            if isinstance(item_owner, QObject) and item_owner is not current:
                current = item_owner
                continue

        parent = current.parent()
        current = parent if isinstance(parent, QObject) else None


def _is_click_away_editor(obj: QObject | None) -> bool:
    if obj is None:
        return False
    try:
        return bool(obj.property(_CLICK_AWAY_EDITOR_PROP))
    except RuntimeError:
        return False


def _find_click_away_editor(obj: QObject | None) -> QObject | None:
    for current in _iter_object_ancestors(obj):
        if _is_click_away_editor(current):
            return current
    return None


class WindowFocusDismissFilter(QObject):
    def refresh_pointer_if_window_active(self) -> None:
        app = QGuiApplication.instance()
        window = self.parent()
        if not isinstance(app, QGuiApplication) or not isinstance(window, QQuickWindow):
            return
        refresh_pointer_if_window_active(app, window, self)

    def on_application_state_changed(self, state: Qt.ApplicationState) -> None:
        if state != Qt.ApplicationState.ApplicationActive:
            return
        self.refresh_pointer_if_window_active()

    def _post_pointer_refresh(
        self, window: QQuickWindow, source_event: QMouseEvent | None = None
    ) -> None:
        if source_event is None:
            global_point = QCursor.pos()
            local_point = window.mapFromGlobal(global_point)
            local_pos = QPointF(local_point)
            global_pos = QPointF(global_point)
        else:
            local_pos = source_event.position()
            global_pos = source_event.globalPosition()

        window_rect = QRectF(0.0, 0.0, float(window.width()), float(window.height()))
        if not window_rect.contains(local_pos):
            return

        move_event = QMouseEvent(
            QEvent.Type.MouseMove,
            local_pos,
            global_pos,
            Qt.MouseButton.NoButton,
            QGuiApplication.mouseButtons(),
            QGuiApplication.keyboardModifiers(),
        )
        QCoreApplication.postEvent(window, move_event)

    def _resolve_focused_editor(self, window: QQuickWindow) -> tuple[QObject, object] | None:
        focus_control = cast(QObject | None, QQmlProperty.read(window, "activeFocusControl"))
        focus_item = cast(QObject | None, window.activeFocusItem())
        focus_owner = _find_click_away_editor(focus_control)
        if focus_owner is None:
            focus_owner = _find_click_away_editor(focus_item)
        if focus_owner is None:
            return None
        hit_test_target = focus_owner if hasattr(focus_owner, "mapFromScene") else focus_item
        if not hasattr(hit_test_target, "mapFromScene"):
            return None
        return focus_owner, hit_test_target

    def _click_is_inside_editor(self, hit_test_target: object, event: QMouseEvent) -> bool:
        map_from_scene = getattr(hit_test_target, "mapFromScene", None)
        contains = getattr(hit_test_target, "contains", None)
        if not callable(map_from_scene) or not callable(contains):
            return False
        local = map_from_scene(event.position())
        return bool(contains(local))

    def _clear_editor_focus(self, editor: QObject) -> None:
        deselect = getattr(editor, "deselect", None)
        if callable(deselect):
            try:
                _ = deselect()
            except Exception:
                pass
        _ = editor.setProperty("focus", False)

    def _defer_editor_blur(self, window: QQuickWindow, editor: QObject) -> None:
        def apply() -> None:
            try:
                if not bool(editor.property("activeFocus")):
                    self._post_pointer_refresh(window)
                    return
                self._clear_editor_focus(editor)
                self._post_pointer_refresh(window)
            except RuntimeError:
                return

        QTimer.singleShot(0, apply)

    @override
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.MouseButtonRelease:
            return False
        if not isinstance(watched, QQuickWindow) or not isinstance(event, QMouseEvent):
            return False

        resolved = self._resolve_focused_editor(watched)
        if resolved is None:
            self._post_pointer_refresh(watched, event)
            return False

        focus_owner, hit_test_target = resolved
        if not self._click_is_inside_editor(hit_test_target, event):
            self._defer_editor_blur(watched, focus_owner)
            return False

        self._post_pointer_refresh(watched, event)
        return False


class HideOnCloseEventFilter(QObject):
    def __init__(
        self,
        window: QQuickWindow,
        *,
        should_hide_on_close: Callable[[], bool],
        on_hide_requested: Callable[[], None],
        on_visibility_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._should_hide_on_close = should_hide_on_close
        self._on_hide_requested = on_hide_requested
        self._on_visibility_changed = on_visibility_changed

    @override
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        window = getattr(self, "_window", None)
        if watched is not window:
            return False
        should_hide_on_close = getattr(self, "_should_hide_on_close", None)
        on_hide_requested = getattr(self, "_on_hide_requested", None)
        on_visibility_changed = getattr(self, "_on_visibility_changed", None)
        if event.type() == QEvent.Type.Close and callable(should_hide_on_close) and should_hide_on_close():
            ignore = getattr(event, "ignore", None)
            if callable(ignore):
                ignore()
            if callable(on_hide_requested):
                on_hide_requested()
            return True
        if (
            callable(on_visibility_changed)
            and event.type() in {QEvent.Type.Show, QEvent.Type.Hide}
        ):
            on_visibility_changed()
        return False


class DesktopTrayController(QObject):
    def __init__(
        self,
        *,
        app: QApplication,
        window: QQuickWindow,
        tray_icon: QSystemTrayIcon,
        preferences: QObject,
        icon_path: Path,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent or app)
        self._app = app
        self._window = window
        self._tray_icon = tray_icon
        self._preferences = preferences
        self._icon_path = icon_path
        self._quitting = False

        self._toggle_action = QAction(self)
        self._quit_action = QAction(self)
        self._menu = QMenu()
        self._menu.addAction(self._toggle_action)
        self._menu.addSeparator()
        self._menu.addAction(self._quit_action)

        self._toggle_action.triggered.connect(self.toggle_window_visibility)
        self._quit_action.triggered.connect(self.request_quit)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.setContextMenu(self._menu)
        self._tray_icon.setToolTip("Bao")
        self._app.aboutToQuit.connect(self._prepare_to_quit)

        self._close_filter = HideOnCloseEventFilter(
            window,
            should_hide_on_close=self.should_hide_on_close,
            on_hide_requested=self.hide_window,
            on_visibility_changed=self.refresh_menu_labels,
        )
        self._window.installEventFilter(self._close_filter)
        self._connect_preference_signals()
        self.refresh_icon()
        self.refresh_menu_labels()
        self._tray_icon.show()

    def should_hide_on_close(self) -> bool:
        return not self._quitting and self._tray_icon.isVisible()

    def _connect_preference_signals(self) -> None:
        for signal_name, slot in (
            ("effectiveLanguageChanged", self.refresh_menu_labels),
            ("isDarkChanged", self.refresh_icon),
        ):
            signal = getattr(self._preferences, signal_name, None)
            if signal is not None:
                _ = signal.connect(slot)

    def _is_dark(self) -> bool:
        return bool(self._preferences.property("isDark"))

    def _tr(self, zh: str, en: str) -> str:
        return zh if effective_desktop_language(self._preferences) == "zh" else en

    @Slot()
    def refresh_menu_labels(self) -> None:
        self._toggle_action.setText(
            self._tr("显示 Bao", "Show Bao")
            if not self._window.isVisible()
            else self._tr("隐藏 Bao", "Hide Bao")
        )
        self._quit_action.setText(self._tr("退出 Bao", "Quit Bao"))

    @Slot()
    def refresh_icon(self) -> None:
        icon = load_tray_icon(self._icon_path, dark_mode=self._is_dark())
        if icon is not None:
            self._tray_icon.setIcon(icon)

    @Slot()
    def restore_window(self) -> None:
        if self._quitting:
            return
        self._window.show()
        self._window.raise_()
        self._window.requestActivate()
        self.refresh_menu_labels()

    @Slot()
    def hide_window(self) -> None:
        if self._quitting:
            return
        self._window.hide()
        self.refresh_menu_labels()

    @Slot()
    def toggle_window_visibility(self) -> None:
        if self._window.isVisible():
            self.hide_window()
            return
        self.restore_window()

    @Slot()
    def request_quit(self) -> None:
        if self._quitting:
            return
        self._prepare_to_quit()
        self._app.quit()

    @Slot()
    def _prepare_to_quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._tray_icon.hide()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.toggle_window_visibility()


def create_desktop_tray_controller(
    *,
    app: QApplication,
    window: QQuickWindow,
    preferences: QObject,
) -> DesktopTrayController | None:
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    tray_icon_path = resolve_tray_icon_path()
    if tray_icon_path is None:
        return None
    tray_icon = load_tray_icon(tray_icon_path, dark_mode=bool(preferences.property("isDark")))
    if tray_icon is None:
        return None
    app.setQuitOnLastWindowClosed(False)
    return DesktopTrayController(
        app=app,
        window=window,
        tray_icon=QSystemTrayIcon(tray_icon, app),
        preferences=preferences,
        icon_path=tray_icon_path,
    )


def refresh_pointer_if_window_active(
    app: QGuiApplication, window: QQuickWindow, focus_filter: WindowFocusDismissFilter
) -> None:
    if app.applicationState() != Qt.ApplicationState.ApplicationActive:
        return
    if not window.isVisible():
        return
    focus_filter._post_pointer_refresh(window)


def install_pointer_refresh_hooks(
    app: QGuiApplication, window: QQuickWindow, focus_filter: WindowFocusDismissFilter
) -> None:
    _ = window
    QTimer.singleShot(0, focus_filter.refresh_pointer_if_window_active)
    _ = app.applicationStateChanged.connect(focus_filter.on_application_state_changed)


def parse_args() -> tuple[bool, str | None, bool, str, bool, str | None]:
    p = argparse.ArgumentParser()
    _ = p.add_argument("--smoke", action="store_true")
    _ = p.add_argument("--qml", default=None)
    _ = p.add_argument("--smoke-theme-toggle", action="store_true")
    _ = p.add_argument("--start-view", choices=("chat", "settings"), default="chat")
    _ = p.add_argument("--seed-messages", action="store_true")
    _ = p.add_argument("--smoke-screenshot", default=None)
    a = p.parse_args()
    smoke = bool(cast(object, a.smoke))
    qml = cast(str | None, a.qml)
    smoke_theme_toggle = bool(cast(object, a.smoke_theme_toggle))
    start_view = cast(str, a.start_view)
    seed_messages = bool(cast(object, a.seed_messages))
    smoke_screenshot = cast(str | None, a.smoke_screenshot)
    return (
        smoke,
        qml,
        smoke_theme_toggle,
        start_view,
        seed_messages,
        smoke_screenshot,
    )


def resolve_qml_path(qml_arg: str | None) -> Path:
    if qml_arg:
        return Path(qml_arg).expanduser().resolve()

    candidates: list[Path] = []
    src_base = Path(__file__).resolve().parent
    candidates.append(src_base / "qml" / "Main.qml")

    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        meipass = getattr(sys, "_MEIPASS", "")
        frozen_roots = [
            Path(meipass) if meipass else None,
            exe.parent,
            exe.parent.parent / "Resources",
            exe.parent.parent / "Resources" / "app",
            exe.parent.parent / "Frameworks",
        ]
        for root in frozen_roots:
            if root is None:
                continue
            candidates.append(root / "qml" / "Main.qml")
            candidates.append(root / "app" / "qml" / "Main.qml")

    for path in candidates:
        if path.exists():
            return path.resolve()

    return candidates[0].resolve()


def _app_resource_candidate_roots() -> list[Path]:
    src_root = Path(__file__).resolve().parent.parent
    roots = [src_root]
    if not getattr(sys, "frozen", False):
        return roots

    exe = Path(sys.executable).resolve()
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        roots.append(Path(meipass))
    roots.extend([exe.parent, exe.parent.parent / "Resources"])

    unique_roots: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_roots.append(resolved)
    return unique_roots


def resolve_app_resource_path(*relative_paths: str) -> Path | None:
    for root in _app_resource_candidate_roots():
        for relative_path in relative_paths:
            path = root / relative_path
            if path.exists():
                return path.resolve()
    return None


def resolve_app_icon_path() -> Path | None:
    if sys.platform == "win32":
        bundled_icon = resolve_app_resource_path(*WINDOWS_APP_ICON_RELATIVE_PATHS)
        if bundled_icon is not None:
            return bundled_icon
        return resolve_app_resource_path(*WINDOWS_APP_ICON_FALLBACK_RELATIVE_PATHS)

    return resolve_app_resource_path(*DEFAULT_APP_ICON_RELATIVE_PATHS)


def resolve_tray_icon_path() -> Path | None:
    return resolve_app_resource_path(*TRAY_APP_ICON_RELATIVE_PATHS) or resolve_app_icon_path()


def resolve_bundled_app_font_path() -> Path | None:
    return resolve_app_resource_path(*BUNDLED_APP_FONT_RELATIVE_PATHS)


def register_qml_resource_bundle() -> bool:
    global _REGISTERED_QML_BUNDLE
    if _REGISTERED_QML_BUNDLE is not None:
        return True
    bundle_path = resolve_app_resource_path(*QML_RCC_RELATIVE_PATHS)
    if bundle_path is None:
        return False
    if not QResource.registerResource(str(bundle_path)):
        return False
    _REGISTERED_QML_BUNDLE = str(bundle_path)
    return True


def resolve_qml_url(qml_arg: str | None) -> QUrl:
    if qml_arg:
        return QUrl.fromLocalFile(str(resolve_qml_path(qml_arg)))
    if register_qml_resource_bundle():
        return QUrl(QML_RESOURCE_MAIN_URL)
    if getattr(sys, "frozen", False):
        return QUrl()
    return QUrl.fromLocalFile(str(resolve_qml_path(None)))


def load_app_icon(icon_path: Path) -> QIcon | None:
    if icon_path.suffix.lower() == ".ico":
        icon = QIcon(str(icon_path))
        return None if icon.isNull() else icon
    return build_rounded_icon(icon_path) or QIcon(str(icon_path))


def _image_alpha_bounds(image: QImage) -> tuple[int, int, int, int] | None:
    left = image.width()
    top = image.height()
    right = -1
    bottom = -1
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() <= 0:
                continue
            left = min(left, x)
            top = min(top, y)
            right = max(right, x)
            bottom = max(bottom, y)
    if right < left or bottom < top:
        return None
    return left, top, right, bottom


def build_tray_mask_image(image_path: Path) -> QImage | None:
    source = QImage(str(image_path)).convertToFormat(QImage.Format.Format_ARGB32)
    if source.isNull():
        return None
    mask = QImage(source.size(), QImage.Format.Format_ARGB32)
    mask.fill(Qt.GlobalColor.transparent)
    threshold = 150
    for y in range(source.height()):
        for x in range(source.width()):
            color = source.pixelColor(x, y)
            alpha = color.alpha()
            if alpha <= 0:
                continue
            if color.lightness() < threshold:
                continue
            mask_alpha = max(0, min(255, alpha))
            mask.setPixelColor(x, y, QColor(255, 255, 255, mask_alpha))
    return mask


def build_monochrome_tray_icon(image_path: Path, *, dark_mode: bool) -> QIcon | None:
    mask = build_tray_mask_image(image_path)
    if mask is None or mask.isNull():
        return None
    bounds = _image_alpha_bounds(mask)
    if bounds is None:
        return None
    left, top, right, bottom = bounds
    trimmed = mask.copy(left, top, right - left + 1, bottom - top + 1)
    icon = QIcon()
    tint = QColor("#FFFFFF" if dark_mode else "#121212")
    for px in (16, 18, 20, 22, 24, 32, 40, 44, 48, 64):
        canvas = QPixmap(px, px)
        canvas.fill(Qt.GlobalColor.transparent)
        padding = max(1.0, px * 0.08)
        target = QRectF(padding, padding, px - padding * 2, px - padding * 2)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(target, trimmed)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(QRectF(0, 0, px, px), tint)
        _ = painter.end()
        icon.addPixmap(canvas)
    if hasattr(icon, "setIsMask"):
        icon.setIsMask(True)
    return None if icon.isNull() else icon


def load_tray_icon(icon_path: Path, *, dark_mode: bool) -> QIcon | None:
    icon = build_monochrome_tray_icon(icon_path, dark_mode=dark_mode)
    if icon is not None:
        return icon
    fallback = QIcon(str(icon_path))
    return None if fallback.isNull() else fallback


def build_rounded_icon(image_path: Path) -> QIcon | None:
    image = QImage(str(image_path))
    if image.isNull():
        return None

    side = min(image.width(), image.height())
    x = (image.width() - side) // 2
    y = (image.height() - side) // 2
    square = image.copy(x, y, side, side)

    icon = QIcon()
    for px in (16, 20, 24, 32, 48, 64, 128, 256, 512):
        canvas = QPixmap(px, px)
        canvas.fill(Qt.GlobalColor.transparent)

        inset = max(1.0, px * 0.06)
        target = QRectF(inset, inset, px - inset * 2, px - inset * 2)
        radius = target.width() * 0.24

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        shadow_path = QPainterPath()
        shadow_rect = QRectF(
            target.x(), target.y() + max(1.0, px * 0.02), target.width(), target.height()
        )
        shadow_path.addRoundedRect(shadow_rect, radius, radius)
        painter.fillPath(shadow_path, QColor(0, 0, 0, 34 if px >= 64 else 22))

        clip = QPainterPath()
        clip.addRoundedRect(target, radius, radius)
        painter.setClipPath(clip)
        painter.drawImage(target, square)

        top_gloss = QLinearGradient(target.left(), target.top(), target.left(), target.bottom())
        top_gloss.setColorAt(0.0, QColor(255, 255, 255, 85 if px >= 64 else 55))
        top_gloss.setColorAt(0.35, QColor(255, 255, 255, 26 if px >= 64 else 18))
        top_gloss.setColorAt(0.65, QColor(255, 255, 255, 0))
        painter.fillPath(clip, top_gloss)

        bottom_tone = QLinearGradient(target.left(), target.top(), target.left(), target.bottom())
        bottom_tone.setColorAt(0.55, QColor(0, 0, 0, 0))
        bottom_tone.setColorAt(1.0, QColor(0, 0, 0, 28 if px >= 64 else 16))
        painter.fillPath(clip, bottom_tone)

        painter.setClipping(False)
        stroke_width = max(1.0, px * 0.012)
        stroke_rect = target.adjusted(
            stroke_width / 2, stroke_width / 2, -stroke_width / 2, -stroke_width / 2
        )
        stroke_pen = QPen(QColor(255, 255, 255, 95 if px >= 64 else 70), stroke_width)
        painter.setPen(stroke_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            stroke_rect, max(1.0, radius - stroke_width / 2), max(1.0, radius - stroke_width / 2)
        )

        inner_pen = QPen(QColor(0, 0, 0, 26 if px >= 64 else 14), max(1.0, px * 0.005))
        painter.setPen(inner_pen)
        inner_rect = stroke_rect.adjusted(1, 1, -1, -1)
        painter.drawRoundedRect(
            inner_rect, max(1.0, radius - stroke_width), max(1.0, radius - stroke_width)
        )

        _ = painter.end()

        icon.addPixmap(canvas)

    return icon


def detect_system_ui_language() -> str:
    candidates: list[str] = []

    sys_locale = QLocale.system()
    try:
        candidates.extend(str(v) for v in sys_locale.uiLanguages())
    except Exception:
        pass
    candidates.append(str(sys_locale.name()))
    candidates.append(str(QLocale().name()))

    if sys.platform == "darwin":
        try:
            raw = subprocess.check_output(
                ["defaults", "read", "-g", "AppleLanguages"],
                text=True,
                timeout=1,
            )
            apple_langs = re.findall(r'"([^"]+)"', raw)
            if apple_langs:
                candidates = apple_langs + candidates
        except Exception:
            pass

    for item in candidates:
        tag = item.strip().lower().replace("_", "-")
        if tag.startswith("zh"):
            return "zh"
        if tag.startswith("en"):
            return "en"
    return "en"


def effective_desktop_language(preferences: QObject) -> str:
    value = preferences.property("effectiveLanguage")
    return value if isinstance(value, str) else "en"


def connect_on_config_change(config_service: object, callback: Callable[[], None]) -> None:
    config_loaded = getattr(config_service, "configLoaded", None)
    save_done = getattr(config_service, "saveDone", None)
    if config_loaded is not None:
        _ = config_loaded.connect(callback)
    if save_done is not None:
        _ = save_done.connect(callback)


def bind_exported_config(config_service: object, apply_fn: Callable[[object], None]) -> None:
    export_data = getattr(config_service, "exportData", None)
    if not callable(export_data):
        return

    def apply_exported_config() -> None:
        apply_fn(export_data())

    apply_exported_config()
    connect_on_config_change(config_service, apply_exported_config)


def preferred_system_font_family() -> str | None:
    families = set(QFontDatabase.families())
    for family in PREFERRED_SYSTEM_FONT_FAMILIES:
        if family in families:
            return family
    return None


def resolve_app_font_family() -> str | None:
    font_path = resolve_bundled_app_font_path()
    if font_path is not None:
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                return families[0]
    return preferred_system_font_family()


def configured_gateway_channels(config_service: object) -> list[str]:
    order = (
        "telegram",
        "discord",
        "whatsapp",
        "feishu",
        "slack",
        "email",
        "qq",
        "dingtalk",
        "imessage",
    )
    get_value = getattr(config_service, "get", None)
    if not callable(get_value):
        return []

    channels: list[str] = []
    for name in order:
        if bool(get_value(f"channels.{name}.enabled", False)):
            channels.append(name)
    return channels


def _apply_windows_rounded_corners(window: QQuickWindow) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        dwmwa_window_corner_preference = 33
        dwmwcp_round = 2
        hwnd = int(window.winId())
        if hwnd == 0:
            return False
        pref = ctypes.c_int(dwmwcp_round)
        result = cast(
            int,
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_uint(dwmwa_window_corner_preference),
                ctypes.byref(pref),
                ctypes.sizeof(pref),
            ),
        )
        return result == 0
    except Exception:
        return False


def _to_qcolor(value: object, fallback: QColor) -> QColor:
    color = QColor(value)
    if color.isValid():
        return color
    return fallback


def _to_colorref(color: QColor) -> int:
    return (color.blue() << 16) | (color.green() << 8) | color.red()


def _apply_windows_titlebar_colors(
    window: QQuickWindow,
    caption_color: QColor,
    text_color: QColor,
) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        dwmwa_caption_color = 35
        dwmwa_text_color = 36
        hwnd = int(window.winId())
        if hwnd == 0:
            return False

        values = (
            (dwmwa_caption_color, _to_colorref(caption_color)),
            (dwmwa_text_color, _to_colorref(text_color)),
        )
        ok = False
        for attr, raw in values:
            val = ctypes.c_uint(raw)
            result = cast(
                int,
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd),
                    ctypes.c_uint(attr),
                    ctypes.byref(val),
                    ctypes.sizeof(val),
                ),
            )
            ok = ok or (result == 0)
        return ok
    except Exception:
        return False


def main() -> int:
    smoke, qml, smoke_theme_toggle, start_view, seed_messages, smoke_screenshot = parse_args()
    from bao.runtime_diagnostics import configure_desktop_logging, report_startup_failure

    _ = configure_desktop_logging()

    qml_url = resolve_qml_url(qml)
    if not qml_url.isValid():
        report_startup_failure(
            "QML load failed: desktop_qml.rcc is required in frozen builds",
            code="qml_resource_missing",
        )
        return 1
    if qml_url.isLocalFile() and not Path(qml_url.toLocalFile()).exists():
        report_startup_failure(
            f"QML load failed: file not found: {qml_url.toLocalFile()}",
            code="qml_missing",
            details={"qml_path": qml_url.toString()},
        )
        return 1

    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"
    if os.getenv("BAO_QML_DISABLE_DISK_CACHE") == "1":
        os.environ["QML_DISABLE_DISK_CACHE"] = "1"
    QQuickStyle.setStyle("Basic")

    fmt = QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    app_font_family = resolve_app_font_family()
    if app_font_family:
        app.setFont(QFont(app_font_family))
    logo_path = resolve_app_icon_path()
    logo_icon: QIcon | None = None
    if logo_path:
        logo_icon = load_app_icon(logo_path)
    if logo_icon:
        app.setWindowIcon(logo_icon)
    engine = QQmlApplicationEngine()

    import importlib

    from app.backend.app_services import AppServices
    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.chat import ChatMessageModel
    from app.backend.config import ConfigService
    from app.backend.diagnostics import DiagnosticsService
    from app.backend.gateway import ChatService
    from app.backend.memory import MemoryService
    from app.backend.preferences import DesktopPreferences
    from app.backend.profile import ProfileService
    from app.backend.profile_binding import DesktopProfileCoordinator
    from app.backend.profile_supervisor import ProfileWorkSupervisorService
    from app.backend.session import SessionService
    from app.backend.skills import SkillsService
    from app.backend.update import UpdateBridge, UpdateService

    cron_module = importlib.import_module("app.backend.cron")
    cron_bridge_service_cls = getattr(cron_module, "CronBridgeService")
    heartbeat_module = importlib.import_module("app.backend.heartbeat")
    heartbeat_bridge_service_cls = getattr(heartbeat_module, "HeartbeatBridgeService")
    tools_module = importlib.import_module("app.backend.tools")
    tools_service_cls = getattr(tools_module, "ToolsService")

    runner = AsyncioRunner()
    runner.start()
    messages_model = ChatMessageModel()
    chat_service = ChatService(messages_model, runner)
    config_service = ConfigService()
    profile_service = ProfileService()
    session_service = SessionService(runner)
    cron_service = cron_bridge_service_cls(runner)
    heartbeat_service = heartbeat_bridge_service_cls(runner)
    memory_service = MemoryService(runner)
    skills_service = SkillsService(runner, "~/.bao/workspace", eager_refresh=False)
    tools_service = tools_service_cls(runner, config_service)
    profile_supervisor_service = ProfileWorkSupervisorService(
        runner,
        profile_service=profile_service,
        session_service=session_service,
        chat_service=chat_service,
        cron_service=cron_service,
        heartbeat_service=heartbeat_service,
    )
    update_service = UpdateService(runner, config_service)
    diagnostics_service = DiagnosticsService(eager_refresh=False)
    update_bridge = UpdateBridge()
    try:
        config_service.load()
    except Exception as exc:
        report_startup_failure(
            f"First-run setup failed: {exc}",
            code="first_run_failed",
        )
        return 1

    system_ui_language = detect_system_ui_language()
    legacy_ui_language = config_service.get("ui.language", "auto")
    desktop_preferences = DesktopPreferences(
        system_ui_language=system_ui_language,
        legacy_ui_language=legacy_ui_language if isinstance(legacy_ui_language, str) else None,
    )
    # Set UI language on ChatService for localized system messages
    set_language = cast(Callable[[str], None], chat_service.setLanguage)
    set_language(effective_desktop_language(desktop_preferences))
    _ = desktop_preferences.effectiveLanguageChanged.connect(
        lambda: set_language(effective_desktop_language(desktop_preferences))
    )
    set_configured_gateway_channels = cast(
        Callable[[list[str]], None], chat_service.setConfiguredGatewayChannels
    )

    def refresh_configured_gateway_channels() -> None:
        set_configured_gateway_channels(configured_gateway_channels(config_service))

    refresh_configured_gateway_channels()
    connect_on_config_change(config_service, refresh_configured_gateway_channels)
    set_config_data = cast(Callable[[object], None], chat_service.setConfigData)
    bind_exported_config(config_service, set_config_data)
    bind_exported_config(config_service, tools_service.setConfigData)
    bind_exported_config(config_service, skills_service.setConfigData)

    set_session_manager = cast(Callable[[object], None], chat_service.setSessionManager)
    _ = session_service.sessionManagerReady.connect(set_session_manager)

    set_gateway_ready = cast(Callable[[], None], session_service.setGatewayReady)
    set_cron_session_service = cast(Callable[[object], None], cron_service.setSessionService)
    set_cron_session_service(session_service)
    set_cron_language = cast(Callable[[str], None], cron_service.setLanguage)
    set_heartbeat_session_service = cast(Callable[[object], None], heartbeat_service.setSessionService)
    set_heartbeat_session_service(session_service)
    set_heartbeat_language = cast(Callable[[str], None], heartbeat_service.setLanguage)
    set_cron_language(effective_desktop_language(desktop_preferences))
    set_heartbeat_language(effective_desktop_language(desktop_preferences))
    _ = desktop_preferences.effectiveLanguageChanged.connect(
        lambda: set_cron_language(effective_desktop_language(desktop_preferences))
    )
    _ = desktop_preferences.effectiveLanguageChanged.connect(
        lambda: set_heartbeat_language(effective_desktop_language(desktop_preferences))
    )
    profile_coordinator = DesktopProfileCoordinator(
        config_service=config_service,
        profile_service=profile_service,
        chat_service=chat_service,
        session_service=session_service,
        memory_service=memory_service,
        cron_service=cron_service,
        heartbeat_service=heartbeat_service,
        skills_service=skills_service,
    )
    _ = profile_service.activeProfileChanged.connect(profile_coordinator.apply_active_profile)
    _ = session_service.sessionManagerReady.connect(profile_coordinator.restart_gateway_if_ready)

    def sync_cron_gateway_state(state: str) -> None:
        cron_service.setGatewayRunning(state == "running")
        heartbeat_service.setGatewayRunning(state == "running")

    sync_cron_gateway_state(cast(str, cast(object, chat_service.state)))
    _ = chat_service.stateChanged.connect(sync_cron_gateway_state)
    _ = getattr(chat_service, "cronServiceChanged").connect(cron_service.setLiveCronService)
    _ = getattr(chat_service, "heartbeatServiceChanged").connect(
        heartbeat_service.setLiveHeartbeatService
    )

    def _on_gateway_ready(sm: object, _ch: object) -> None:
        set_gateway_ready()
        session_service.initialize(sm)

    _ = chat_service.gatewayReady.connect(_on_gateway_ready)
    # Wire session → gateway: when active session changes, update gateway session key
    set_session_key = cast(Callable[[str], None], chat_service.setSessionKey)
    _ = session_service.activeKeyChanged.connect(set_session_key)
    set_session_summary = cast(
        Callable[[str, object, object], None], chat_service.setSessionSummary
    )
    _ = session_service.activeSummaryChanged.connect(set_session_summary)
    set_active_session_read_only = cast(
        Callable[[bool], None], chat_service.setActiveSessionReadOnly
    )

    def sync_active_session_meta() -> None:
        set_active_session_read_only(session_service.property("activeSessionReadOnly"))

    sync_active_session_meta()
    _ = session_service.activeSessionMetaChanged.connect(sync_active_session_meta)
    notify_startup_session_ready = cast(
        Callable[[str], None], chat_service.notifyStartupSessionReady
    )
    _ = session_service.startupTargetReady.connect(notify_startup_session_ready)
    # Wire session deletion → gateway: cancel streaming if needed
    handle_deleted = cast(Callable[[str, bool, str], None], chat_service.handle_session_deleted)
    _ = session_service.deleteCompleted.connect(handle_deleted)
    connect_on_config_change(config_service, profile_coordinator.refresh_from_config)
    connect_on_config_change(config_service, profile_supervisor_service.refresh)
    _ = update_bridge.checkRequested.connect(update_service.check_for_updates)
    _ = update_bridge.installRequested.connect(update_service.install_update)
    _ = update_bridge.reloadRequested.connect(update_service.reloadConfig)
    _ = update_service.quitRequested.connect(app.quit)

    context = engine.rootContext()
    app_services = AppServices(
        chat_service=chat_service,
        config_service=config_service,
        profile_service=profile_service,
        session_service=session_service,
        cron_service=cron_service,
        heartbeat_service=heartbeat_service,
        profile_supervisor_service=profile_supervisor_service,
        memory_service=memory_service,
        skills_service=skills_service,
        tools_service=tools_service,
        update_service=update_service,
        diagnostics_service=diagnostics_service,
        update_bridge=update_bridge,
        desktop_preferences=desktop_preferences,
        messages_model=messages_model,
        system_ui_language=system_ui_language,
    )
    context.setContextProperty("appServices", app_services)

    engine.load(qml_url)
    if not engine.rootObjects():
        report_startup_failure(
            f"QML load failed: {qml_url.toString()}",
            code="qml_load_failed",
            details={"qml_path": qml_url.toString()},
        )
        return 1

    root = engine.rootObjects()[0]
    if logo_icon and isinstance(root, QQuickWindow):
        root.setIcon(logo_icon)
    if isinstance(root, QQuickWindow):
        setattr(
            app,
            "_desktop_tray_controller",
            create_desktop_tray_controller(
                app=app,
                window=root,
                preferences=desktop_preferences,
            ),
        )
    _ = profile_supervisor_service.profileNavigationRequested.connect(
        lambda section: (
            root.setProperty("startView", "chat"),
            root.setProperty("activeWorkspace", section),
        )
    )
    use_native_title_bar = True
    _ = root.setProperty("useNativeTitleBar", use_native_title_bar)
    focus_dismiss_filter: WindowFocusDismissFilter | None = None
    if isinstance(root, QQuickWindow):
        focus_dismiss_filter = WindowFocusDismissFilter(root)
        app_instance = QGuiApplication.instance()
        if isinstance(app_instance, QGuiApplication):
            install_pointer_refresh_hooks(app_instance, root, focus_dismiss_filter)
        root.installEventFilter(focus_dismiss_filter)
        if not use_native_title_bar:
            root.setColor(QColor(0, 0, 0, 0))
        elif sys.platform == "win32":
            caption_color = _to_qcolor(cast(object, root.property("bgBase")), QColor("#0C0C14"))
            text_color = _to_qcolor(cast(object, root.property("textPrimary")), QColor("#E8E8F0"))

            def _apply_windows_chrome() -> None:
                _ = _apply_windows_rounded_corners(root)
                _ = _apply_windows_titlebar_colors(root, caption_color, text_color)

            QTimer.singleShot(
                0,
                _apply_windows_chrome,
            )
    _ = root.setProperty("startView", start_view)

    def _run_deferred_startup() -> None:
        profile_coordinator.refresh_from_config()
        profile_supervisor_service.refresh()
        update_service.reloadConfig()
        diagnostics_service.refresh()

    QTimer.singleShot(16, _run_deferred_startup)

    if seed_messages:
        _ = messages_model.append_user("Hello, what can you do?")
        _ = messages_model.append_assistant(
            "I can help with code, writing, analysis, and more!", status="done"
        )

    if smoke_screenshot:
        out = Path(smoke_screenshot).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        def _snap() -> None:
            if isinstance(root, QQuickWindow):
                ok = root.grabWindow().save(str(out))
                if not ok:
                    print(f"Smoke screenshot save failed: {out}", file=sys.stderr)
            app.quit()

        QTimer.singleShot(250, _snap)
    elif smoke_theme_toggle:
        toggle_theme = cast(Callable[[], None], desktop_preferences.toggleTheme)
        QTimer.singleShot(100, toggle_theme)
        QTimer.singleShot(500, app.quit)
    elif smoke:
        QTimer.singleShot(500, app.quit)

    ret = app.exec()
    stop_chat = cast(Callable[[], None], chat_service.stop)
    stop_chat()
    shutdown_memory = cast(Callable[[], None], memory_service.shutdown)
    shutdown_memory()
    runner.shutdown(grace_s=2.0)
    return ret


if __name__ == "__main__":
    raise SystemExit(main())
