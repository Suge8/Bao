from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bao.agent.tool_exposure import ToolExposureSnapshot


@dataclass
class RunArtifactPayloadRequest:
    run_kind: str
    session_key: str
    model: str | None
    started_at: str
    finished_at: str
    user_request: str
    tool_signal_text: str | None
    final_content: str | None
    exit_reason: str
    provider_finish_reason: str
    provider_error: bool
    interrupted: bool
    total_errors: int
    tools_used: list[str]
    tool_trace: list[str]
    reasoning_snippets: list[str]
    last_state_text: str | None
    tool_exposure_history: list[ToolExposureSnapshot]
    tool_observability: dict[str, Any]
    diagnostics_snapshot: dict[str, Any]


def build_run_artifact_payload(request: RunArtifactPayloadRequest) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_kind": request.run_kind,
        "session_key": request.session_key,
        "model": request.model,
        "started_at": request.started_at,
        "finished_at": request.finished_at,
        "user_request": request.user_request,
        "tool_signal_text": request.tool_signal_text or "",
        "summary_strategy": {
            "prompt_summary_preserved": True,
            "last_state_text_present": bool(request.last_state_text),
            "reasoning_snippet_count": len(request.reasoning_snippets),
        },
        "result": {
            "exit_reason": request.exit_reason,
            "provider_finish_reason": request.provider_finish_reason,
            "provider_error": request.provider_error,
            "interrupted": request.interrupted,
            "total_errors": request.total_errors,
            "final_content": request.final_content,
        },
        "tooling": {
            "tools_used": list(request.tools_used),
            "tool_trace": list(request.tool_trace),
            "tool_exposure_history": [
                snapshot.as_record() for snapshot in request.tool_exposure_history
            ],
            "tool_observability": dict(request.tool_observability),
        },
        "diagnostics": request.diagnostics_snapshot,
    }
