from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from bao.agent.subagent import SubagentManager, TaskStatus
from bao.agent.tools.diagnostics import RuntimeDiagnosticsTool
from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider
from bao.runtime_diagnostics import get_runtime_diagnostics_store


class _DummyProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(api_key=None, api_base=None)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        on_progress=None,
        **kwargs: Any,
    ) -> Any:
        del messages, tools, model, max_tokens, temperature, on_progress, kwargs
        raise RuntimeError("not used in this test")

    def get_default_model(self) -> str:
        return "dummy/model"


def test_runtime_diagnostics_tool_returns_structured_snapshot() -> None:
    store = get_runtime_diagnostics_store()
    store.clear()
    store.set_log_file_path("/tmp/bao-desktop.log")
    store.append_log_line("2026-03-07 10:00:00 | INFO | boot")
    store.record_event(
        source="tool",
        stage="tool_call",
        message="Exit code 1",
        code="exec_exit_code",
        retryable=True,
        details={"tool_name": "exec"},
    )
    store.set_tool_observability({"tool_calls_total": 3, "tool_calls_error": 1})

    tool = RuntimeDiagnosticsTool(store=store)
    result = asyncio.run(tool.execute(max_events=3, include_logs=True, max_log_lines=10))
    payload = json.loads(result)

    assert payload["log_file_path"] == "/tmp/bao-desktop.log"
    assert payload["event_count"] == 1
    assert payload["recent_events"][0]["code"] == "exec_exit_code"
    assert payload["recent_events"][0]["details"]["tool_name"] == "exec"
    assert payload["tool_observability"]["tool_calls_total"] == 3
    assert payload["recent_log_lines"] == ["2026-03-07 10:00:00 | INFO | boot"]


def test_runtime_diagnostics_tool_applies_scope_filters() -> None:
    store = get_runtime_diagnostics_store()
    store.clear()
    store.record_event(
        source="subagent",
        stage="failed",
        message="subagent failed",
        code="subagent_failed",
        session_key="task-1",
    )
    store.record_event(
        source="agent_loop",
        stage="dispatch",
        message="parent failed",
        code="message_error",
        session_key="desktop:local",
    )
    store.append_log_line("2026-03-07 10:00:00 | ERROR | parent failed")
    store.set_tool_observability({"tool_calls_total": 9})

    subagent_tool = RuntimeDiagnosticsTool(
        store=store,
        allowed_sources=("subagent",),
        pinned_session_key="task-1",
        allow_logs=False,
        allow_tool_observability=False,
    )
    result = asyncio.run(subagent_tool.execute(include_logs=True, source="agent_loop"))
    payload = json.loads(result)

    assert payload["event_count"] == 0
    assert "recent_log_lines" not in payload
    assert "tool_observability" not in payload

    own_result = asyncio.run(subagent_tool.execute(include_logs=True))
    own_payload = json.loads(own_result)

    assert own_payload["event_count"] == 1
    assert own_payload["recent_events"][0]["source"] == "subagent"
    assert own_payload["recent_events"][0]["session_key"] == "task-1"


def test_runtime_diagnostics_tool_hides_global_views_for_scoped_parent_query() -> None:
    store = get_runtime_diagnostics_store()
    store.clear()
    store.record_event(
        source="provider",
        stage="chat",
        message="provider failed",
        code="provider_error",
        session_key="desktop:local",
    )
    store.append_log_line("2026-03-07 10:00:00 | ERROR | provider failed")
    store.set_tool_observability({"tool_calls_total": 4})

    tool = RuntimeDiagnosticsTool(store=store)
    payload = json.loads(
        asyncio.run(tool.execute(source="provider", session_key="desktop:local", include_logs=True))
    )

    assert payload["event_count"] == 1
    assert payload["recent_events"][0]["code"] == "provider_error"
    assert "recent_log_lines" not in payload
    assert "tool_observability" not in payload


def test_subagent_failure_records_runtime_diagnostic(tmp_path: Path) -> None:
    store = get_runtime_diagnostics_store()
    store.clear()

    manager = SubagentManager(
        provider=_DummyProvider(),
        workspace=tmp_path,
        bus=MessageBus(),
    )
    manager._task_statuses["task-1"] = TaskStatus(
        task_id="task-1",
        label="demo",
        task_description="run demo",
        origin={"channel": "desktop", "chat_id": "local", "session_key": "desktop:local"},
    )

    asyncio.run(
        manager._finalize_subagent_failure(
            task_id="task-1",
            label="demo",
            task="run demo",
            origin={"channel": "desktop", "chat_id": "local", "session_key": "desktop:local"},
            error=RuntimeError("subagent exploded"),
        )
    )

    snapshot = store.snapshot(max_events=4, max_log_lines=0)
    assert snapshot["event_count"] == 1
    assert snapshot["recent_events"][0]["source"] == "subagent"
    assert snapshot["recent_events"][0]["stage"] == "failed"
    assert snapshot["recent_events"][0]["details"]["task_id"] == "task-1"
