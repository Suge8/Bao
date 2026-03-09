"""Tools for checking and cancelling background subagent tasks."""

import json
import time
from typing import TYPE_CHECKING, Any

from bao.agent import shared
from bao.agent.tools.base import Tool

if TYPE_CHECKING:
    from bao.agent.subagent import SubagentManager, TaskStatus


class CheckTasksTool(Tool):
    def __init__(self, manager: "SubagentManager"):
        self._manager = manager

    @property
    def name(self) -> str:
        return "check_tasks"

    @property
    def description(self) -> str:
        return "Check status of background tasks by task.task_id from spawn, or list all."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Optional: check a specific task by ID. Omit to list all.",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> str:
        task_id = kwargs.get("task_id")
        if task_id is not None:
            task_id = str(task_id).strip()
            if not task_id:
                return "Error: task_id must be a non-empty string"
        if task_id:
            st = self._manager.get_task_status(task_id)
            if not st:
                return f"No task found with id '{task_id}'."
            return _format_detailed(st)

        all_statuses = self._manager.get_all_statuses()
        if not all_statuses:
            return "No background tasks."

        running = [s for s in all_statuses if s.status == "running"]
        finished = [s for s in all_statuses if s.status != "running"]

        parts: list[str] = []
        if running:
            parts.append(f"Running ({len(running)}):")
            for s in running:
                parts.append(_format_brief(s))
        if finished:
            nl = "\n" if running else ""
            shown = sorted(finished, key=lambda x: x.updated_at, reverse=True)[:5]
            total = len(finished)
            count_hint = f" — showing {len(shown)} of {total}" if total > 5 else ""
            parts.append(f"{nl}Recent finished ({total}){count_hint}:")
            for s in shown:
                parts.append(_format_brief(s))
        return "\n".join(parts)


class CancelTaskTool(Tool):
    def __init__(self, manager: "SubagentManager"):
        self._manager = manager

    @property
    def name(self) -> str:
        return "cancel_task"

    @property
    def description(self) -> str:
        return "Cancel a running background task by task.task_id from spawn."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the task to cancel",
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, **kwargs: Any) -> str:
        task_id = kwargs.get("task_id")
        if task_id is not None:
            task_id = str(task_id).strip()
        if not isinstance(task_id, str) or not task_id:
            return "Error: task_id is required"
        return await self._manager.cancel_task(task_id)


def _format_brief(st: "TaskStatus") -> str:
    """Compact single-line format for list view."""
    now = time.time()
    elapsed = max(0, int(now - st.started_at))
    mins, secs = divmod(elapsed, 60)
    time_str = f"{mins}m{secs}s" if mins else f"{secs}s"
    label = shared.sanitize_visible_text(st.label)
    stale_warning = ""
    if st.status == "running" and now - st.updated_at > 120:
        stale_warning = " ⚠️ stale"

    if st.status == "running":
        line = (
            f"  [{st.task_id}] {label}"
            f" | {st.status} | {st.iteration}/{st.max_iterations} iters"
            f" | {time_str}{stale_warning}"
        )
    else:
        line = f"  [{st.task_id}] {label} | {st.status} | {time_str}"
        if st.result_summary:
            cleaned = shared.sanitize_visible_text(st.result_summary)
            summary = cleaned[:80]
            if len(cleaned) > 80:
                summary += "..."
            line += f" → {summary}"
    return line


def _format_detailed(st: "TaskStatus") -> str:
    """Multi-line format for single-task query."""
    now = time.time()
    elapsed = max(0, int(now - st.started_at))
    mins, secs = divmod(elapsed, 60)
    time_str = f"{mins}m{secs}s" if mins else f"{secs}s"
    label = shared.sanitize_visible_text(st.label)
    stale_warning = ""
    if st.status == "running" and now - st.updated_at > 120:
        stale_warning = " ⚠️ no update for >2min"

    line = (
        f"  [{st.task_id}] {label}\n"
        f"  status: {st.status} | {st.iteration}/{st.max_iterations} iters"
        f" | {st.tool_steps} tools | phase: {st.phase} | {time_str}{stale_warning}"
    )
    if st.result_summary and st.status in ("completed", "failed"):
        cleaned = shared.sanitize_visible_text(st.result_summary)
        summary = cleaned[:300]
        if len(cleaned) > 300:
            summary += "..."
        line += f"\n  result: {summary}"
    recent_actions = getattr(st, "recent_actions", [])
    if recent_actions and st.status == "running":
        line += "\n  recent: " + "; ".join(
            shared.sanitize_visible_text(str(a)) for a in recent_actions[-3:]
        )
    return line


def _task_to_snapshot(st: "TaskStatus") -> dict[str, Any]:
    """Convert a TaskStatus to a stable JSON-serialisable dict (schema_version=1).

    Fields are whitelisted — internal fields like resume_context are excluded.
    """

    # Sanitise visible strings the same way text outputs do.
    def _clean(s: str | None) -> str | None:
        if s is None:
            return None
        return shared.sanitize_visible_text(s)

    recent = [_clean(str(a)) or "" for a in (getattr(st, "recent_actions", []) or [])[-3:]]
    last_error: dict[str, Any] = {
        "category": getattr(st, "last_error_category", None),
        "code": getattr(st, "last_error_code", None),
        "message": getattr(st, "last_error_message", None),
    }
    return {
        "task_id": st.task_id,
        "child_session_key": st.child_session_key,
        "label": _clean(st.label),
        "status": st.status,
        "iteration": st.iteration,
        "max_iterations": st.max_iterations,
        "tool_steps": st.tool_steps,
        "phase": st.phase,
        "started_at": st.started_at,
        "updated_at": st.updated_at,
        "result_summary": _clean(st.result_summary),
        "recent_actions": recent,
        "last_error": last_error,
        "origin": {
            "channel": st.origin.get("channel", ""),
            "chat_id": st.origin.get("chat_id", ""),
        },
    }


class CheckTasksJsonTool(Tool):
    """Return machine-readable task snapshot(s) as JSON (schema_version=1)."""

    def __init__(self, manager: "SubagentManager"):
        self._manager = manager

    @property
    def name(self) -> str:
        return "check_tasks_json"

    @property
    def description(self) -> str:
        return "Return structured JSON snapshot of background tasks (schema_version=1)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "schema_version": {
                    "type": "integer",
                    "description": "Schema version to use (default: 1).",
                },
                "task_id": {
                    "type": "string",
                    "description": "Optional: return snapshot for a single task.",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> str:
        raw_schema_version = kwargs.get("schema_version", 1)
        try:
            schema_version = int(raw_schema_version)
        except (TypeError, ValueError):
            return json.dumps(
                {
                    "schema_version": 1,
                    "error": {
                        "code": "invalid_schema_version",
                        "message": (
                            "schema_version must be an integer-compatible value "
                            f"(got {raw_schema_version!r})."
                        ),
                    },
                }
            )
        if schema_version != 1:
            return json.dumps(
                {
                    "schema_version": 1,
                    "error": {
                        "code": "unsupported_schema_version",
                        "message": f"Unsupported schema_version: {schema_version}. Only 1 is supported.",
                    },
                }
            )

        task_id = kwargs.get("task_id")
        if task_id is not None:
            task_id = str(task_id).strip()
            if not task_id:
                return json.dumps(
                    {
                        "schema_version": 1,
                        "error": {
                            "code": "invalid_task_id",
                            "message": "task_id must be a non-empty string.",
                        },
                    }
                )

        if task_id:
            st = self._manager.get_task_status(task_id)
            if not st:
                return json.dumps(
                    {
                        "schema_version": 1,
                        "error": {
                            "code": "task_not_found",
                            "message": f"No task found with id '{task_id}'.",
                        },
                    }
                )
            return json.dumps(
                {
                    "schema_version": 1,
                    "generated_at": time.time(),
                    "tasks": [_task_to_snapshot(st)],
                }
            )

        all_statuses = self._manager.get_all_statuses()
        return json.dumps(
            {
                "schema_version": 1,
                "generated_at": time.time(),
                "tasks": [_task_to_snapshot(s) for s in all_statuses],
            }
        )
