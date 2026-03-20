from __future__ import annotations

from typing import Any


class HubTaskDirectory:
    """Read-only view over background child-session task state."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def get_status(self, task_id: str) -> Any | None:
        get_task_status = getattr(self._runtime, "get_task_status", None)
        if not callable(get_task_status):
            return None
        normalized_task_id = _normalize_task_id(task_id)
        if not normalized_task_id:
            return None
        return get_task_status(normalized_task_id)

    def list_statuses(self) -> list[Any]:
        get_all_statuses = getattr(self._runtime, "get_all_statuses", None)
        if not callable(get_all_statuses):
            return []
        statuses = get_all_statuses()
        return list(statuses) if isinstance(statuses, list) else []


class HubTaskControl:
    """Minimal mutation facade for background child-session tasks."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    async def cancel(self, task_id: str) -> str:
        cancel_task = getattr(self._runtime, "cancel_task", None)
        if not callable(cancel_task):
            return "Error: task control not configured"
        normalized_task_id = _normalize_task_id(task_id)
        if not normalized_task_id:
            return "Error: task_id is required"
        return await cancel_task(normalized_task_id)


def _normalize_task_id(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()
