from __future__ import annotations

from typing import Any

from bao.agent.tool_exposure import ToolExposureSnapshot


def build_run_artifact_payload(
    *,
    run_kind: str,
    session_key: str,
    model: str | None,
    started_at: str,
    finished_at: str,
    user_request: str,
    tool_signal_text: str | None,
    final_content: str | None,
    exit_reason: str,
    provider_finish_reason: str,
    provider_error: bool,
    interrupted: bool,
    total_errors: int,
    tools_used: list[str],
    tool_trace: list[str],
    reasoning_snippets: list[str],
    last_state_text: str | None,
    tool_exposure_history: list[ToolExposureSnapshot],
    tool_observability: dict[str, Any],
    diagnostics_snapshot: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_kind": run_kind,
        "session_key": session_key,
        "model": model,
        "started_at": started_at,
        "finished_at": finished_at,
        "user_request": user_request,
        "tool_signal_text": tool_signal_text or "",
        "summary_strategy": {
            "prompt_summary_preserved": True,
            "last_state_text_present": bool(last_state_text),
            "reasoning_snippet_count": len(reasoning_snippets),
        },
        "result": {
            "exit_reason": exit_reason,
            "provider_finish_reason": provider_finish_reason,
            "provider_error": provider_error,
            "interrupted": interrupted,
            "total_errors": total_errors,
            "final_content": final_content,
        },
        "tooling": {
            "tools_used": list(tools_used),
            "tool_trace": list(tool_trace),
            "tool_exposure_history": [snapshot.as_record() for snapshot in tool_exposure_history],
            "tool_observability": dict(tool_observability),
        },
        "diagnostics": diagnostics_snapshot,
    }
