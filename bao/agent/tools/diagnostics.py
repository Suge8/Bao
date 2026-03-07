from __future__ import annotations

import json
from typing import Any, Iterable

from bao.agent.tools.base import Tool
from bao.runtime_diagnostics import RuntimeDiagnosticsStore, get_runtime_diagnostics_store


class RuntimeDiagnosticsTool(Tool):
    def __init__(
        self,
        store: RuntimeDiagnosticsStore | None = None,
        *,
        allowed_sources: Iterable[str] | None = None,
        pinned_session_key: str | None = None,
        allow_logs: bool = True,
        allow_tool_observability: bool = True,
    ) -> None:
        self._store = store or get_runtime_diagnostics_store()
        self._allowed_sources = tuple(
            str(source).strip() for source in (allowed_sources or ()) if str(source).strip()
        )
        self._pinned_session_key = str(pinned_session_key or "").strip()
        self._allow_logs = allow_logs
        self._allow_tool_observability = allow_tool_observability

    @property
    def name(self) -> str:
        return "runtime_diagnostics"

    @property
    def description(self) -> str:
        return "Read structured runtime diagnostics for recent internal failures and observability."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "max_events": {
                    "type": "integer",
                    "description": "Maximum number of recent diagnostic events to return.",
                    "minimum": 1,
                    "maximum": 20,
                },
                "include_logs": {
                    "type": "boolean",
                    "description": "Include a recent log tail excerpt when extra context is needed.",
                },
                "max_log_lines": {
                    "type": "integer",
                    "description": "Maximum number of recent log lines when include_logs is true.",
                    "minimum": 1,
                    "maximum": 200,
                },
                "source": {
                    "type": "string",
                    "description": "Optional source filter such as subagent, tool, provider, or agent_loop.",
                },
                "session_key": {
                    "type": "string",
                    "description": "Optional session/task filter when you need diagnostics for one scoped run.",
                },
            },
        }

    async def execute(self, **kwargs: Any) -> str:
        max_events = int(kwargs.get("max_events", 6) or 6)
        include_logs = bool(kwargs.get("include_logs", False))
        max_log_lines = int(kwargs.get("max_log_lines", 40) or 40)
        requested_source = str(kwargs.get("source") or "").strip()
        requested_session_key = str(kwargs.get("session_key") or "").strip()

        allowed_sources, blocked = self._resolve_sources(requested_source)
        if blocked:
            return self._render_payload(
                event_count=0,
                log_file_path=self._store.snapshot(max_events=0, max_log_lines=0)["log_file_path"],
                recent_events=[],
                tool_observability={},
                recent_log_lines=[],
                include_logs=include_logs,
                include_tool_observability=False,
            )

        effective_session_key = self._pinned_session_key or requested_session_key
        allowed_session_keys = [effective_session_key] if effective_session_key else []
        scoped_read = bool(allowed_sources or allowed_session_keys)

        snapshot = self._store.snapshot(
            max_events=max_events,
            max_log_lines=max_log_lines,
            allowed_sources=allowed_sources,
            allowed_session_keys=allowed_session_keys,
        )
        return self._render_payload(
            event_count=int(snapshot["event_count"]),
            log_file_path=str(snapshot["log_file_path"]),
            recent_events=list(snapshot["recent_events"]),
            tool_observability=dict(snapshot["tool_observability"]),
            recent_log_lines=list(snapshot["recent_log_lines"]),
            include_logs=include_logs and not scoped_read,
            include_tool_observability=not scoped_read,
        )

    def _resolve_sources(self, requested_source: str) -> tuple[list[str], bool]:
        if not self._allowed_sources:
            return ([requested_source] if requested_source else []), False
        if not requested_source:
            return list(self._allowed_sources), False
        if requested_source in self._allowed_sources:
            return [requested_source], False
        return [], True

    def _render_payload(
        self,
        *,
        event_count: int,
        log_file_path: str,
        recent_events: list[dict[str, Any]],
        tool_observability: dict[str, Any],
        recent_log_lines: list[str],
        include_logs: bool,
        include_tool_observability: bool,
    ) -> str:
        payload: dict[str, Any] = {
            "log_file_path": log_file_path,
            "event_count": event_count,
            "recent_events": recent_events,
        }
        if self._allow_tool_observability and include_tool_observability:
            payload["tool_observability"] = tool_observability
        if include_logs and self._allow_logs:
            payload["recent_log_lines"] = recent_log_lines
        return json.dumps(payload, ensure_ascii=False, indent=2)
