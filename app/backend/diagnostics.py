from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, ClassVar

from PySide6.QtCore import Property, QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from bao.runtime_diagnostics import get_runtime_diagnostics_store


class DiagnosticsService(QObject):
    changed: ClassVar[Signal] = Signal()
    _storeUpdated: ClassVar[Signal] = Signal()

    def __init__(self, parent: QObject | None = None, *, eager_refresh: bool = True) -> None:
        super().__init__(parent)
        self._store = get_runtime_diagnostics_store()
        self._update_lock = RLock()
        self._refresh_queued = False
        self._refresh_dirty = False
        self._log_file_path = ""
        self._recent_log_text = ""
        self._events: list[dict[str, Any]] = []
        self._observability_items: list[dict[str, str]] = []
        self._event_count = 0
        self._store.add_listener(self._on_store_change)
        _ = self.destroyed.connect(self._detach_store_listener)
        _ = self._storeUpdated.connect(self._drain_store_updates, Qt.ConnectionType.QueuedConnection)
        if eager_refresh:
            self.refresh()

    def _on_store_change(self) -> None:
        with self._update_lock:
            self._refresh_dirty = True
            if self._refresh_queued:
                return
            self._refresh_queued = True
        self._storeUpdated.emit()

    @Slot()
    def _drain_store_updates(self) -> None:
        while True:
            with self._update_lock:
                self._refresh_dirty = False
            self.refresh()
            with self._update_lock:
                if not self._refresh_dirty:
                    self._refresh_queued = False
                    return

    def _detach_store_listener(self, *_args: object) -> None:
        self._store.remove_listener(self._on_store_change)

    @Property(str, notify=changed)
    def logFilePath(self) -> str:
        return self._log_file_path

    @Property(str, notify=changed)
    def recentLogText(self) -> str:
        return self._recent_log_text

    @Property(list, notify=changed)
    def events(self) -> list[dict[str, Any]]:
        return self._events

    @Property(list, notify=changed)
    def observabilityItems(self) -> list[dict[str, str]]:
        return self._observability_items

    @Property(int, notify=changed)
    def eventCount(self) -> int:
        return self._event_count

    @Slot()
    def refresh(self) -> None:
        snapshot = self._store.snapshot(max_events=8, max_log_lines=160)
        self._log_file_path = str(snapshot.get("log_file_path") or "")
        self._recent_log_text = "\n".join(snapshot.get("recent_log_lines", []))
        self._events = list(snapshot.get("recent_events", []))
        self._event_count = int(snapshot.get("event_count", 0) or 0)
        observability = snapshot.get("tool_observability", {})
        self._observability_items = self._build_observability_items(observability)
        self.changed.emit()

    @Slot()
    def openLogDirectory(self) -> None:
        if not self._log_file_path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self._log_file_path).parent)))

    @Slot(result=str)
    def buildAssistantPrompt(self) -> str:
        snapshot = self._store.snapshot(max_events=5, max_log_lines=0)
        recent_events = snapshot.get("recent_events", [])
        if not recent_events:
            return ""
        lines = [
            "Please analyze these runtime diagnostics and explain the likely cause, impacted layer, and next debugging step.",
            "If the issue is not actionable, say that clearly.",
            "",
            f"Log file: {snapshot.get('log_file_path') or 'N/A'}",
            "",
            "Recent structured diagnostics:",
        ]
        for event in recent_events:
            if not isinstance(event, dict):
                continue
            code = str(event.get("code") or event.get("stage") or "event")
            message = str(event.get("message") or "")
            source = str(event.get("source") or "")
            lines.append(f"- [{code}] {message} ({source})")

        observability = snapshot.get("tool_observability", {})
        if isinstance(observability, dict) and observability:
            lines.extend(
                [
                    "",
                    "Tool observability:",
                    str(observability),
                ]
            )

        return "\n".join(lines)

    @staticmethod
    def _build_observability_items(summary: dict[str, Any]) -> list[dict[str, str]]:
        if not isinstance(summary, dict) or not summary:
            return []
        fields = (
            ("tool_calls_total", "Tool calls"),
            ("tool_calls_error", "Tool errors"),
            ("execution_errors", "Exec errors"),
            ("retry_rate_proxy", "Retry rate"),
        )
        items: list[dict[str, str]] = []
        for key, label in fields:
            value = summary.get(key)
            if value is None:
                continue
            if isinstance(value, float):
                text = f"{value:.2f}"
            else:
                text = str(value)
            items.append({"label": label, "value": text})
        return items
