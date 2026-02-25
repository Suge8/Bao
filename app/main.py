from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QLocale, QObject, QTimer, Slot
from PySide6.QtGui import QColor, QGuiApplication, QSurfaceFormat
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle


class ThemeManager(QObject):
    def __init__(self) -> None:
        super().__init__()
        self._is_dark: bool = True

    @Slot()
    def toggle_theme(self) -> None:
        self._is_dark = not self._is_dark


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
    chat_service = ChatService(messages_model)
    config_service = ConfigService()
    session_service = SessionService(runner)
    theme_manager = ThemeManager()

    from bao.config.loader import ensure_first_run
    ensure_first_run()

    config_service.load()

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
    if isinstance(root, QQuickWindow):
        root.setColor(QColor(0, 0, 0, 0))
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
