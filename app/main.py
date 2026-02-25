from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QLocale, QObject, QTimer, Signal, Slot, Property
from PySide6.QtGui import QColor, QGuiApplication, QSurfaceFormat
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle


class ThemeManager(QObject):
    isDarkChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._is_dark: bool = True

    @Property(bool, notify=isDarkChanged)
    def isDark(self) -> bool:
        return self._is_dark

    @Slot()
    def toggle_theme(self) -> None:
        self._is_dark = not self._is_dark
        self.isDarkChanged.emit()


def parse_args() -> tuple[bool, str | None, bool, str, bool, str | None]:
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--qml", default=None)
    p.add_argument("--smoke-theme-toggle", action="store_true")
    p.add_argument("--start-view", choices=("chat", "settings"), default="chat")
    p.add_argument("--seed-messages", action="store_true")
    p.add_argument("--smoke-screenshot", default=None)
    a = p.parse_args()
    return (
        a.smoke,
        a.qml,
        a.smoke_theme_toggle,
        a.start_view,
        a.seed_messages,
        a.smoke_screenshot,
    )


def resolve_qml_path(qml_arg: str | None) -> Path:
    if qml_arg:
        return Path(qml_arg).expanduser().resolve()
    return (Path(__file__).resolve().parent / "qml" / "Main.qml").resolve()


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
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            ctypes.c_uint(dwmwa_window_corner_preference),
            ctypes.byref(pref),
            ctypes.sizeof(pref),
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
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_uint(attr),
                ctypes.byref(val),
                ctypes.sizeof(val),
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
    logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {message}")

    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"
    os.environ["QML_DISABLE_DISK_CACHE"] = "1"
    QQuickStyle.setStyle("Basic")

    fmt = QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()

    from app.backend.chat import ChatMessageModel
    from app.backend.gateway import ChatService
    from app.backend.session import SessionService
    from app.backend.config import ConfigService
    from app.backend.asyncio_runner import AsyncioRunner

    runner = AsyncioRunner()
    runner.start()
    messages_model = ChatMessageModel()
    chat_service = ChatService(messages_model, runner)
    config_service = ConfigService()
    session_service = SessionService(runner)
    theme_manager = ThemeManager()

    from bao.config.loader import ensure_first_run

    ensure_first_run()

    config_service.load()

    # Set UI language on ChatService for localized system messages
    _cfg_lang = config_service.get("ui.language", "auto")
    _ui_lang = _cfg_lang if _cfg_lang in ("zh", "en") else detect_system_ui_language()
    chat_service.setLanguage(_ui_lang)

    # Early SessionManager for browsing history without gateway
    from bao.session.manager import SessionManager

    _ws = Path(config_service.get("agents.defaults.workspace", "~/.bao/workspace")).expanduser()
    _ws.mkdir(parents=True, exist_ok=True)
    session_service.initialize(SessionManager(_ws))

    # Wire gateway → session: when gateway is ready, initialize session service
    chat_service.gatewayReady.connect(lambda sm, _ch: session_service.initialize(sm))
    # Wire session → gateway: when active session changes, update gateway session key
    session_service.activeKeyChanged.connect(chat_service.setSessionKey)

    context = engine.rootContext()
    context.setContextProperty("chatService", chat_service)
    context.setContextProperty("configService", config_service)
    context.setContextProperty("sessionService", session_service)
    context.setContextProperty("themeManager", theme_manager)
    context.setContextProperty("messagesModel", messages_model)
    context.setContextProperty("systemUiLanguage", detect_system_ui_language())

    engine.load(str(qml_path))
    if not engine.rootObjects():
        print(f"QML load failed: {qml_path}", file=sys.stderr)
        return 1

    root = engine.rootObjects()[0]
    use_native_title_bar = True
    _ = root.setProperty("useNativeTitleBar", use_native_title_bar)
    if isinstance(root, QQuickWindow):
        if not use_native_title_bar:
            root.setColor(QColor(0, 0, 0, 0))
        elif sys.platform == "win32":
            caption_color = _to_qcolor(root.property("bgBase"), QColor("#0C0C14"))
            text_color = _to_qcolor(root.property("textPrimary"), QColor("#E8E8F0"))
            border_color = _to_qcolor(root.property("borderSubtle"), caption_color)
            QTimer.singleShot(
                0,
                lambda: (
                    _apply_windows_rounded_corners(root),
                    _apply_windows_titlebar_colors(root, caption_color, text_color, border_color),
                ),
            )
    _ = root.setProperty("startView", start_view)


    if seed_messages:
        messages_model.append_user("Hello, what can you do?")
        messages_model.append_assistant(
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
    chat_service.stop()
    runner.shutdown(grace_s=2.0)
    return ret


if __name__ == "__main__":
    raise SystemExit(main())
