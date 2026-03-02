from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, ClassVar, TypeVar, cast

from PySide6.QtCore import Property, QLocale, QObject, QRectF, Qt, QTimer, Signal, Slot
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QSurfaceFormat,
)
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle

_F = TypeVar("_F", bound=Callable[..., object])


def _typed_slot(
    *types: type[object] | str,
    name: str | None = None,
    result: type[object] | str | None = None,
) -> Callable[[_F], _F]:
    if name is None and result is None:
        slot_decorator = Slot(*types)
    elif result is None:
        slot_decorator = Slot(*types, name=name)
    elif name is None:
        slot_decorator = Slot(*types, result=result)
    else:
        slot_decorator = Slot(*types, name=name, result=result)
    return cast(Callable[[_F], _F], slot_decorator)


class ThemeManager(QObject):
    isDarkChanged: ClassVar[Signal] = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._is_dark: bool = True

    @Property(bool, notify=isDarkChanged)
    def isDark(self) -> bool:
        return self._is_dark

    @_typed_slot()
    def toggle_theme(self) -> None:
        self._is_dark = not self._is_dark
        self.isDarkChanged.emit()


class ClipboardService(QObject):
    @_typed_slot(str, name="copyText")
    def copy_text(self, text: str) -> None:
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text or "")


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


def resolve_logo_path() -> Path | None:
    candidates: list[Path] = []
    src_root = Path(__file__).resolve().parent.parent
    candidates.extend(
        [
            src_root / "assets" / "logo.jpg",
            src_root / "assets" / "logo.jpeg",
            src_root / "assets" / "logo.png",
        ]
    )

    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        meipass = getattr(sys, "_MEIPASS", "")
        frozen_roots = [
            Path(meipass) if meipass else None,
            exe.parent,
            exe.parent.parent / "Resources",
        ]
        for root in frozen_roots:
            if root is None:
                continue
            candidates.extend(
                [
                    root / "assets" / "logo.jpg",
                    root / "assets" / "logo.jpeg",
                    root / "assets" / "logo.png",
                ]
            )

    for path in candidates:
        if path.exists():
            return path.resolve()
    return None


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
    border_color: QColor,
) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        dwmwa_border_color = 34
        dwmwa_caption_color = 35
        dwmwa_text_color = 36
        hwnd = int(window.winId())
        if hwnd == 0:
            return False

        values = (
            (dwmwa_caption_color, _to_colorref(caption_color)),
            (dwmwa_text_color, _to_colorref(text_color)),
            (dwmwa_border_color, _to_colorref(border_color)),
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
    qml_path = resolve_qml_path(qml)
    if not qml_path.exists():
        print(f"QML load failed: file not found: {qml_path}", file=sys.stderr)
        return 1

    # --- loguru setup (mirrors CLI _setup_logging) ---
    import logging

    from loguru import logger

    logger.remove()
    logging.basicConfig(level=logging.WARNING)
    for name in ("httpcore", "httpx", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)
    _ = logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {message}")

    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"
    os.environ["QML_DISABLE_DISK_CACHE"] = "1"
    QQuickStyle.setStyle("Basic")

    fmt = QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QGuiApplication(sys.argv)
    logo_path = resolve_logo_path()
    logo_icon: QIcon | None = None
    if logo_path:
        logo_icon = build_rounded_icon(logo_path) or QIcon(str(logo_path))
    if logo_icon:
        app.setWindowIcon(logo_icon)
    engine = QQmlApplicationEngine()

    from app.backend.asyncio_runner import AsyncioRunner
    from app.backend.chat import ChatMessageModel
    from app.backend.config import ConfigService
    from app.backend.gateway import ChatService
    from app.backend.session import SessionService

    runner = AsyncioRunner()
    runner.start()
    messages_model = ChatMessageModel()
    chat_service = ChatService(messages_model, runner)
    config_service = ConfigService()
    session_service = SessionService(runner)
    theme_manager = ThemeManager()
    clipboard_service = ClipboardService()

    from bao.config.loader import ensure_first_run

    _ = ensure_first_run()

    config_service.load()

    # Set UI language on ChatService for localized system messages
    _cfg_lang = config_service.get("ui.language", "auto")
    _ui_lang = _cfg_lang if _cfg_lang in ("zh", "en") else detect_system_ui_language()
    set_language = cast(Callable[[str], None], chat_service.setLanguage)
    set_language(_ui_lang)

    # Early SessionManager for browsing history without gateway
    from bao.session.manager import SessionManager

    workspace_value = config_service.get("agents.defaults.workspace", "~/.bao/workspace")
    workspace_str = workspace_value if isinstance(workspace_value, str) else "~/.bao/workspace"
    _ws = Path(workspace_str).expanduser()
    _ws.mkdir(parents=True, exist_ok=True)
    _early_sm = SessionManager(_ws)
    session_service.initialize(_early_sm)
    set_session_manager = cast(Callable[[object], None], chat_service.setSessionManager)
    set_session_manager(_early_sm)

    set_gateway_ready = cast(Callable[[], None], session_service.setGatewayReady)

    def _on_gateway_ready(sm: object, _ch: object) -> None:
        set_gateway_ready()
        session_service.initialize(sm)

    _ = chat_service.gatewayReady.connect(_on_gateway_ready)
    # Wire session → gateway: when active session changes, update gateway session key
    set_session_key = cast(Callable[[str], None], chat_service.setSessionKey)
    _ = session_service.activeKeyChanged.connect(set_session_key)

    context = engine.rootContext()
    context.setContextProperty("chatService", chat_service)
    context.setContextProperty("configService", config_service)
    context.setContextProperty("sessionService", session_service)
    context.setContextProperty("themeManager", theme_manager)
    context.setContextProperty("clipboardService", clipboard_service)
    context.setContextProperty("messagesModel", messages_model)
    context.setContextProperty("systemUiLanguage", detect_system_ui_language())

    engine.load(str(qml_path))
    if not engine.rootObjects():
        print(f"QML load failed: {qml_path}", file=sys.stderr)
        return 1

    root = engine.rootObjects()[0]
    if logo_icon and isinstance(root, QQuickWindow):
        root.setIcon(logo_icon)
    use_native_title_bar = True
    _ = root.setProperty("useNativeTitleBar", use_native_title_bar)
    if isinstance(root, QQuickWindow):
        if not use_native_title_bar:
            root.setColor(QColor(0, 0, 0, 0))
        elif sys.platform == "win32":
            caption_color = _to_qcolor(cast(object, root.property("bgBase")), QColor("#0C0C14"))
            text_color = _to_qcolor(cast(object, root.property("textPrimary")), QColor("#E8E8F0"))
            border_color = _to_qcolor(cast(object, root.property("borderSubtle")), caption_color)

            def _apply_windows_chrome() -> None:
                _ = _apply_windows_rounded_corners(root)
                _ = _apply_windows_titlebar_colors(root, caption_color, text_color, border_color)

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
        QTimer.singleShot(100, theme_manager.toggle_theme)
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
