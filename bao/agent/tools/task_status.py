"""Tools for checking and cancelling background subagent tasks."""

from typing import TYPE_CHECKING, Any

from bao.agent.tools._task_status_format import (
    format_brief as _format_brief,
)
from bao.agent.tools._task_status_format import (
    format_detailed as _format_detailed,
)
from bao.agent.tools._task_status_json import (
    build_snapshot_payload,
    normalize_task_id,
    task_not_found_payload,
    validate_schema_version,
)
from bao.agent.tools.base import Tool
from bao.hub import HubTaskControl, HubTaskDirectory

if TYPE_CHECKING:
    from bao.agent.subagent import SubagentManager


class CheckTasksTool(Tool):
    def __init__(
        self,
        manager: "SubagentManager | HubTaskDirectory",
    ):
        self._directory = _coerce_directory(manager)

    @property
    def name(self) -> str:
        return "check_tasks"

    @property
    def description(self) -> str:
        return (
            "Check status of background child-session tasks by task.task_id from spawn, "
            "or list all."
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
        if task_id is not None:
            task_id = str(task_id).strip()
            if not task_id:
                return "Error: task_id must be a non-empty string"
        if task_id:
            st = self._directory.get_status(task_id)
            if not st:
                return f"No task found with id '{task_id}'."
            return _format_detailed(st)

        all_statuses = self._directory.list_statuses()
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
    def __init__(
        self,
        manager: "SubagentManager | HubTaskControl",
    ):
        self._control = _coerce_control(manager)

    @property
    def name(self) -> str:
        return "cancel_task"

    @property
    def description(self) -> str:
        return "Cancel a running background child-session task by task.task_id from spawn."

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
        return await self._control.cancel(task_id)


class CheckTasksJsonTool(Tool):
    """Return machine-readable task snapshot(s) as JSON (schema_version=1)."""

    def __init__(
        self,
        manager: "SubagentManager | HubTaskDirectory",
    ):
        self._directory = _coerce_directory(manager)

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
        schema_version, schema_error = validate_schema_version(kwargs.get("schema_version", 1))
        del schema_version
        if schema_error:
            return schema_error
        task_id, task_error = normalize_task_id(kwargs.get("task_id"))
        if task_error:
            return task_error
        if task_id:
            status = self._directory.get_status(task_id)
            if not status:
                return task_not_found_payload(task_id)
            return build_snapshot_payload([status])
        return build_snapshot_payload(self._directory.list_statuses())


def _coerce_directory(manager: "SubagentManager | HubTaskDirectory") -> HubTaskDirectory:
    if isinstance(manager, HubTaskDirectory):
        return manager
    return HubTaskDirectory(manager)


def _coerce_control(manager: "SubagentManager | HubTaskControl") -> HubTaskControl:
    if isinstance(manager, HubTaskControl):
        return manager
    return HubTaskControl(manager)
