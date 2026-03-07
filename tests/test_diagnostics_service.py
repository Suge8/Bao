from __future__ import annotations

import importlib
from typing import Any, cast

from bao.runtime_diagnostics import get_runtime_diagnostics_store

pytest = importlib.import_module("pytest")
QtGui = pytest.importorskip("PySide6.QtGui")
QGuiApplication = QtGui.QGuiApplication


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QGuiApplication.instance() or QGuiApplication([])
    yield app


def test_diagnostics_service_projects_store_snapshot(qt_app) -> None:
    from app.backend.diagnostics import DiagnosticsService

    store = get_runtime_diagnostics_store()
    store.clear()
    store.set_log_file_path("/tmp/bao-desktop.log")
    store.append_log_line("2026-03-07 10:00:00 | INFO | boot")
    store.record_event(
        source="provider",
        stage="chat",
        message="model timeout",
        code="provider_error",
        retryable=True,
    )
    store.set_tool_observability({"tool_calls_total": 5, "tool_calls_error": 2})

    service = DiagnosticsService()
    service.refresh()
    qt_app.processEvents()

    recent_log_text = cast(str, service.property("recentLogText"))
    event_count = cast(int, service.property("eventCount"))
    events = cast(list[dict[str, Any]], service.property("events"))
    observability_items = cast(list[dict[str, str]], service.property("observabilityItems"))

    assert service.logFilePath == "/tmp/bao-desktop.log"
    assert "boot" in recent_log_text
    assert event_count == 1
    assert events[0]["code"] == "provider_error"
    assert observability_items[0]["label"] == "Tool calls"
    assert observability_items[0]["value"] == "5"


def test_diagnostics_service_builds_assistant_prompt(qt_app) -> None:
    from app.backend.diagnostics import DiagnosticsService

    store = get_runtime_diagnostics_store()
    store.clear()
    store.set_log_file_path("/tmp/bao-desktop.log")
    store.append_log_line("2026-03-07 10:00:00 | ERROR | timeout")
    store.record_event(
        source="subagent",
        stage="failed",
        message="Error: provider timeout",
        code="provider_error",
        retryable=False,
    )

    service = DiagnosticsService()
    prompt = service.buildAssistantPrompt()

    assert "provider timeout" in prompt
    assert "Recent structured diagnostics" in prompt
    assert "Recent log tail" not in prompt


def test_diagnostics_service_omits_empty_assistant_prompt(qt_app) -> None:
    from app.backend.diagnostics import DiagnosticsService

    store = get_runtime_diagnostics_store()
    store.clear()
    store.set_log_file_path("/tmp/bao-desktop.log")
    store.append_log_line("2026-03-07 10:00:00 | INFO | boot")

    service = DiagnosticsService()

    assert service.buildAssistantPrompt() == ""
