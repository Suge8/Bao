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
        return (
            "Check the status of background tasks. "
            "Use when the user asks about task progress, status, "
            "or anything like 'how is it going', 'is it done yet', 'what tasks are running'."
        )

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
            return _format_status(st)

        all_statuses = self._manager.get_all_statuses()
        if not all_statuses:
            return "No background tasks."

        running = [s for s in all_statuses if s.status == "running"]
        finished = [s for s in all_statuses if s.status != "running"]

        parts: list[str] = []
        if running:
            parts.append(f"Running ({len(running)}):")
            for s in running:
                parts.append(_format_status(s))
        if finished:
            parts.append(f"\nRecent finished ({len(finished)}):")
            for s in sorted(finished, key=lambda x: x.updated_at, reverse=True)[:5]:
                parts.append(_format_status(s))
        return "\n".join(parts)


class CancelTaskTool(Tool):
    def __init__(self, manager: "SubagentManager"):
        self._manager = manager

    @property
    def name(self) -> str:
        return "cancel_task"

    @property
    def description(self) -> str:
        return (
            "Cancel a running background task. "
            "Use when the user wants to stop a task that is currently running."
        )

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


def _format_status(st: "TaskStatus") -> str:

    elapsed = int(time.time() - st.started_at)
    mins, secs = divmod(elapsed, 60)
    time_str = f"{mins}m{secs}s" if mins else f"{secs}s"
    stale_warning = ""
    if st.status == "running" and time.time() - st.updated_at > 120:
        stale_warning = " ⚠️ no update for >2min"

    line = (
        f"  [{st.task_id}] {st.label} | {st.status} | "
        f"{st.iteration}/{st.max_iterations} iters, {st.tool_steps} tools | "
        f"phase: {st.phase} | {time_str}{stale_warning}"
    )
    if st.result_summary and st.status in ("completed", "failed"):
        summary = st.result_summary[:200]
        if len(st.result_summary) > 200:
            summary += "..."
        line += f"\n    → {summary}"
    # Show recent actions for running tasks (helps main agent understand what subagent is doing)
    recent_actions = getattr(st, "recent_actions", [])
    if recent_actions and st.status == "running":
        line += "\n    → recent: " + "; ".join(recent_actions[-3:])
    offloaded_count = int(getattr(st, "offloaded_count", 0) or 0)
    offloaded_chars = int(getattr(st, "offloaded_chars", 0) or 0)
    clipped_count = int(getattr(st, "clipped_count", 0) or 0)
    clipped_chars = int(getattr(st, "clipped_chars", 0) or 0)
    if offloaded_count or clipped_count:
        line += (
            "\n    → budget: "
            f"offload {offloaded_count}/{offloaded_chars} chars, "
            f"clip {clipped_count}/{clipped_chars} chars"
        )
    return line
