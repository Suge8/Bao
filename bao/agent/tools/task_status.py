"""Tools for checking and cancelling background subagent tasks."""

import time
from typing import TYPE_CHECKING, Any

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
        return "Check status of background tasks (by task_id or list all)."

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
        if task_id is not None and not isinstance(task_id, str):
            return "Error: task_id must be a string"
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
            parts.append(f"{nl}Recent finished ({len(finished)}):")
            for s in sorted(finished, key=lambda x: x.updated_at, reverse=True)[:5]:
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
        return "Cancel a running background task by task_id."

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
        if not isinstance(task_id, str) or not task_id:
            return "Error: task_id is required"
        return await self._manager.cancel_task(task_id)


def _format_brief(st: "TaskStatus") -> str:
    """Compact single-line format for list view."""
    now = time.time()
    elapsed = max(0, int(now - st.started_at))
    mins, secs = divmod(elapsed, 60)
    time_str = f"{mins}m{secs}s" if mins else f"{secs}s"
    label = st.label.replace("\n", " ").replace("\r", "")
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
            cleaned = st.result_summary.replace("\n", " ").replace("\r", "")
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
    label = st.label.replace("\n", " ").replace("\r", "")
    stale_warning = ""
    if st.status == "running" and now - st.updated_at > 120:
        stale_warning = " ⚠️ no update for >2min"

    line = (
        f"  [{st.task_id}] {label}\n"
        f"  status: {st.status} | {st.iteration}/{st.max_iterations} iters"
        f" | {st.tool_steps} tools | phase: {st.phase} | {time_str}{stale_warning}"
    )
    if st.result_summary and st.status in ("completed", "failed"):
        cleaned = st.result_summary.replace("\n", " ").replace("\r", "")
        summary = cleaned[:300]
        if len(cleaned) > 300:
            summary += "..."
        line += f"\n  result: {summary}"
    recent_actions = getattr(st, "recent_actions", [])
    if recent_actions and st.status == "running":
        line += "\n  recent: " + "; ".join(str(a).replace("\n", " ").replace("\r", "") for a in recent_actions[-3:])
    return line
