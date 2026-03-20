from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from bao.agent import shared

if TYPE_CHECKING:
    from bao.agent.subagent import TaskStatus


def _clean_visible(value: str | None) -> str | None:
    if value is None:
        return None
    return shared.sanitize_visible_text(value)


def _elapsed_time_parts(status: "TaskStatus") -> tuple[str, float]:
    now = time.time()
    elapsed = max(0, int(now - status.started_at))
    mins, secs = divmod(elapsed, 60)
    time_text = f"{mins}m{secs}s" if mins else f"{secs}s"
    return time_text, now


def format_brief(status: "TaskStatus") -> str:
    time_text, now = _elapsed_time_parts(status)
    label = shared.sanitize_visible_text(status.label)
    stale_warning = ""
    if status.status == "running" and now - status.updated_at > 120:
        stale_warning = " ⚠️ stale"
    if status.status == "running":
        return (
            f"  [{status.task_id}] {label}"
            f" | {status.status} | {status.iteration}/{status.max_iterations} iters"
            f" | {time_text}{stale_warning}"
        )
    line = f"  [{status.task_id}] {label} | {status.status} | {time_text}"
    if status.result_summary:
        cleaned = shared.sanitize_visible_text(status.result_summary)
        summary = cleaned[:80]
        if len(cleaned) > 80:
            summary += "..."
        line += f" → {summary}"
    return line


def format_detailed(status: "TaskStatus") -> str:
    time_text, now = _elapsed_time_parts(status)
    label = shared.sanitize_visible_text(status.label)
    stale_warning = ""
    if status.status == "running" and now - status.updated_at > 120:
        stale_warning = " ⚠️ no update for >2min"
    line = (
        f"  [{status.task_id}] {label}\n"
        f"  status: {status.status} | {status.iteration}/{status.max_iterations} iters"
        f" | {status.tool_steps} tools | phase: {status.phase} | {time_text}{stale_warning}"
    )
    if status.result_summary and status.status in ("completed", "failed"):
        cleaned = shared.sanitize_visible_text(status.result_summary)
        summary = cleaned[:300]
        if len(cleaned) > 300:
            summary += "..."
        line += f"\n  result: {summary}"
    recent_actions = getattr(status, "recent_actions", [])
    if recent_actions and status.status == "running":
        line += "\n  recent: " + "; ".join(
            shared.sanitize_visible_text(str(item)) for item in recent_actions[-3:]
        )
    return line


def task_to_snapshot(status: "TaskStatus") -> dict[str, Any]:
    recent = [
        _clean_visible(str(item)) or ""
        for item in (getattr(status, "recent_actions", []) or [])[-3:]
    ]
    last_error = {
        "category": getattr(status, "last_error_category", None),
        "code": getattr(status, "last_error_code", None),
        "message": getattr(status, "last_error_message", None),
    }
    return {
        "task_id": status.task_id,
        "child_session_key": status.child_session_key,
        "label": _clean_visible(status.label),
        "status": status.status,
        "iteration": status.iteration,
        "max_iterations": status.max_iterations,
        "tool_steps": status.tool_steps,
        "phase": status.phase,
        "started_at": status.started_at,
        "updated_at": status.updated_at,
        "result_summary": _clean_visible(status.result_summary),
        "recent_actions": recent,
        "last_error": last_error,
        "origin": {
            "channel": status.origin.get("channel", ""),
            "chat_id": status.origin.get("chat_id", ""),
        },
    }
