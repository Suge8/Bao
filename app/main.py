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
    Qt,
    QTimer,
)
from PySide6.QtGui import (
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


def _inherits_text_editor(obj: QObject | None) -> bool:
    meta = obj.metaObject() if obj is not None else None
    while meta is not None:
        name = meta.className()
        if any(token in name for token in ("TextArea", "TextField", "TextInput", "TextEdit")):
            return True
        meta = meta.superClass()
    return False


class WindowFocusDismissFilter(QObject):
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
            local_pos,
            global_pos,
            Qt.MouseButton.NoButton,
            QGuiApplication.mouseButtons(),
            QGuiApplication.keyboardModifiers(),
        )
        QCoreApplication.postEvent(window, move_event)

    def _resolve_focused_editor(self, window: QQuickWindow) -> tuple[QObject, object] | None:
        focus_control = cast(QObject | None, QQmlProperty.read(window, "activeFocusControl"))
        focus_item = window.activeFocusItem()
        focus_owner = focus_control if _inherits_text_editor(focus_control) else focus_item
        if not _inherits_text_editor(focus_owner):
            return None
        editor = cast(QObject, focus_owner)
        hit_test_target = editor if hasattr(editor, "mapFromScene") else focus_item
        if not hasattr(hit_test_target, "mapFromScene"):
            return None
        return editor, hit_test_target

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
            self._clear_editor_focus(focus_owner)
        self._post_pointer_refresh(watched, event)
        return False


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


def resolve_bundled_app_font_path() -> Path | None:
    return resolve_app_resource_path(*BUNDLED_APP_FONT_RELATIVE_PATHS)


def load_app_icon(icon_path: Path) -> QIcon | None:
    if icon_path.suffix.lower() == ".ico":
        icon = QIcon(str(icon_path))
        return None if icon.isNull() else icon
    return build_rounded_icon(icon_path) or QIcon(str(icon_path))


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

    qml_path = resolve_qml_path(qml)
    if not qml_path.exists():
        report_startup_failure(
            f"QML load failed: file not found: {qml_path}",
            code="qml_missing",
            details={"qml_path": str(qml_path)},
        )
        return 1

    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"
    os.environ["QML_DISABLE_DISK_CACHE"] = "1"
    QQuickStyle.setStyle("Basic")

    fmt = QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QGuiApplication(sys.argv)
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

    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.chat import ChatMessageModel
    from app.backend.config import ConfigService
    from app.backend.diagnostics import DiagnosticsService
    from app.backend.gateway import ChatService
    from app.backend.preferences import DesktopPreferences
    from app.backend.session import SessionService
    from app.backend.update import UpdateBridge, UpdateService

    runner = AsyncioRunner()
    runner.start()
    messages_model = ChatMessageModel()
    chat_service = ChatService(messages_model, runner)
    config_service = ConfigService()
    session_service = SessionService(runner)
    update_service = UpdateService(runner, config_service)
    diagnostics_service = DiagnosticsService()
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
    update_service.reloadConfig()

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
    _ = config_service.configLoaded.connect(refresh_configured_gateway_channels)
    _ = config_service.saveDone.connect(refresh_configured_gateway_channels)
    set_config_data = cast(Callable[[object], None], chat_service.setConfigData)
    set_config_data(config_service.exportData())
    _ = config_service.configLoaded.connect(lambda: set_config_data(config_service.exportData()))
    _ = config_service.saveDone.connect(lambda: set_config_data(config_service.exportData()))

    workspace_value = config_service.get("agents.defaults.workspace", "~/.bao/workspace")
    workspace_str = workspace_value if isinstance(workspace_value, str) else "~/.bao/workspace"
    _ws = Path(workspace_str).expanduser()
    set_session_manager = cast(Callable[[object], None], chat_service.setSessionManager)
    _ = session_service.sessionManagerReady.connect(set_session_manager)

    set_gateway_ready = cast(Callable[[], None], session_service.setGatewayReady)

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
    bootstrap_workspace = cast(Callable[[str], None], session_service.bootstrapWorkspace)
    bootstrap_workspace(str(_ws))
    _ = update_bridge.checkRequested.connect(update_service.check_for_updates)
    _ = update_bridge.installRequested.connect(update_service.install_update)
    _ = update_bridge.reloadRequested.connect(update_service.reloadConfig)
    _ = update_service.quitRequested.connect(app.quit)

    context = engine.rootContext()
    context.setContextProperty("chatService", chat_service)
    context.setContextProperty("configService", config_service)
    context.setContextProperty("sessionService", session_service)
    context.setContextProperty("updateService", update_service)
    context.setContextProperty("diagnosticsService", diagnostics_service)
    context.setContextProperty("updateBridge", update_bridge)
    context.setContextProperty("desktopPreferences", desktop_preferences)
    context.setContextProperty("messagesModel", messages_model)
    context.setContextProperty("systemUiLanguage", system_ui_language)

    engine.load(str(qml_path))
    if not engine.rootObjects():
        report_startup_failure(
            f"QML load failed: {qml_path}",
            code="qml_load_failed",
            details={"qml_path": str(qml_path)},
        )
        return 1

    root = engine.rootObjects()[0]
    if logo_icon and isinstance(root, QQuickWindow):
        root.setIcon(logo_icon)
    use_native_title_bar = True
    _ = root.setProperty("useNativeTitleBar", use_native_title_bar)
    focus_dismiss_filter: WindowFocusDismissFilter | None = None
    if isinstance(root, QQuickWindow):
        focus_dismiss_filter = WindowFocusDismissFilter(root)
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
    runner.shutdown(grace_s=2.0)
    return ret


if __name__ == "__main__":
    raise SystemExit(main())
