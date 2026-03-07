from __future__ import annotations

import logging
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Iterable

from loguru import logger

_MAX_EVENT_COUNT = 48
_MAX_LOG_LINE_COUNT = 600


def _sanitize_text(value: Any, *, max_len: int = 400) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    compact = " ".join(text.split())
    if len(compact) <= max_len:
        return compact
    omitted = len(compact) - max_len
    return f"{compact[:max_len]}… (+{omitted} chars)"


def _sanitize_value(value: Any, *, max_len: int = 400) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_text(value, max_len=max_len)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {
            _sanitize_text(key, max_len=80): _sanitize_value(item, max_len=max_len)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(item, max_len=max_len) for item in value]
    return _sanitize_text(value, max_len=max_len)


class RuntimeDiagnosticsStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._recent_events: deque[dict[str, Any]] = deque(maxlen=_MAX_EVENT_COUNT)
        self._recent_log_lines: deque[str] = deque(maxlen=_MAX_LOG_LINE_COUNT)
        self._tool_observability: dict[str, Any] = {}
        self._log_file_path = ""
        self._listeners: list[Callable[[], None]] = []

    def clear(self) -> None:
        with self._lock:
            self._recent_events.clear()
            self._recent_log_lines.clear()
            self._tool_observability = {}
            self._log_file_path = ""
        self._notify_listeners()

    def set_log_file_path(self, path: str | Path) -> None:
        with self._lock:
            self._log_file_path = str(Path(path).expanduser()) if path else ""
        self._notify_listeners()

    def append_log_line(self, line: str) -> None:
        cleaned = str(line or "").rstrip("\n")
        if not cleaned:
            return
        with self._lock:
            self._recent_log_lines.append(cleaned)
        self._notify_listeners()

    def record_event(
        self,
        *,
        source: str,
        stage: str,
        message: str,
        level: str = "error",
        code: str = "",
        retryable: bool | None = None,
        session_key: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        event = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "level": (level or "info").lower(),
            "source": _sanitize_text(source, max_len=80),
            "stage": _sanitize_text(stage, max_len=80),
            "code": _sanitize_text(code, max_len=80),
            "message": _sanitize_text(message, max_len=240),
            "retryable": retryable,
            "session_key": _sanitize_text(session_key, max_len=120),
            "details": _sanitize_value(details or {}, max_len=200),
        }
        with self._lock:
            self._recent_events.appendleft(event)
        self._notify_listeners()

    def set_tool_observability(self, summary: dict[str, Any] | None) -> None:
        with self._lock:
            sanitized = _sanitize_value(summary or {}, max_len=120)
            self._tool_observability = sanitized if isinstance(sanitized, dict) else {}
        self._notify_listeners()

    def add_listener(self, listener: Callable[[], None]) -> None:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[], None]) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def snapshot(
        self,
        *,
        max_events: int = 8,
        max_log_lines: int = 120,
        allowed_sources: Iterable[str] | None = None,
        allowed_session_keys: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        event_limit = max(0, int(max_events))
        log_limit = max(0, int(max_log_lines))
        source_filter = {
            _sanitize_text(source, max_len=80)
            for source in (allowed_sources or ())
            if str(source).strip()
        }
        session_filter = {
            _sanitize_text(session_key, max_len=120)
            for session_key in (allowed_session_keys or ())
            if str(session_key).strip()
        }
        with self._lock:
            recent_events = list(self._recent_events)
            if source_filter:
                recent_events = [
                    event
                    for event in recent_events
                    if str(event.get("source") or "") in source_filter
                ]
            if session_filter:
                recent_events = [
                    event
                    for event in recent_events
                    if str(event.get("session_key") or "") in session_filter
                ]
            return {
                "log_file_path": self._log_file_path,
                "recent_events": recent_events[:event_limit],
                "recent_log_lines": list(self._recent_log_lines)[-log_limit:] if log_limit else [],
                "tool_observability": dict(self._tool_observability),
                "event_count": len(recent_events),
                "log_line_count": len(self._recent_log_lines),
            }

    def _notify_listeners(self) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener()
            except Exception:
                continue


_STORE = RuntimeDiagnosticsStore()


def get_runtime_diagnostics_store() -> RuntimeDiagnosticsStore:
    return _STORE


def configure_desktop_logging(log_file_path: str | Path | None = None) -> Path:

    from bao.config.loader import get_data_dir

    target = (
        Path(log_file_path).expanduser()
        if log_file_path
        else get_data_dir() / "logs" / "desktop.log"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    store = get_runtime_diagnostics_store()
    store.set_log_file_path(target)

    logger.remove()
    logging.basicConfig(level=logging.WARNING, force=True)
    for name in ("httpcore", "httpx", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)

    console_format = "{time:HH:mm:ss} | {message}"
    file_format = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}"

    logger.add(sys.stderr, level="INFO", format=console_format)
    logger.add(
        str(target),
        level="DEBUG",
        rotation="5 MB",
        retention=5,
        encoding="utf-8",
        format=file_format,
    )
    logger.add(
        lambda message: store.append_log_line(str(message).rstrip("\n")),
        level="DEBUG",
        format=file_format,
    )
    return target
