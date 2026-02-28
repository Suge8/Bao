"""Spawn tool for creating background subagents."""

from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from bao.agent.tools.base import Tool

if TYPE_CHECKING:
    from bao.agent.subagent import SubagentManager


class SpawnTool(Tool):
    """
    Tool to spawn a subagent for background task execution.

    The subagent runs asynchronously and announces its result back
    to the main agent when complete.
    """

    def __init__(self, manager: "SubagentManager"):
        self._manager = manager
        self._origin_channel: ContextVar[str] = ContextVar(
            "spawn_origin_channel", default="gateway"
        )
        self._origin_chat_id: ContextVar[str] = ContextVar("spawn_origin_chat_id", default="direct")
        self._session_key: ContextVar[str] = ContextVar(
            "spawn_session_key", default="gateway:direct"
        )

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        """Set the origin context for subagent announcements."""
        self._origin_channel.set(channel)
        self._origin_chat_id.set(chat_id)
        self._session_key.set(session_key or f"{channel}:{chat_id}")

    @property
    def name(self) -> str:
        return "spawn"

    @property
    def description(self) -> str:
        return (
            "Delegate a task to a background subagent. Returns task_id for tracking."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task for the subagent to complete",
                },
                "label": {
                    "type": "string",
                    "description": "Optional short label for the task (for display)",
                },
                "context_from": {
                    "type": "string",
                    "description": "task_id of a completed/failed task whose result provides context",
                },
            },
            "required": ["task"],
        }

    async def execute(self, **kwargs: Any) -> str:
        """Spawn a subagent to execute the given task."""
        task = kwargs.get("task")
        label = kwargs.get("label")
        context_from = kwargs.get("context_from")
        if not isinstance(task, str) or not task:
            return "Spawn failed: task text is required"
        if label is not None and not isinstance(label, str):
            return "Spawn failed: label must be a string"
        return await self._manager.spawn(
            task=task,
            label=label,
            origin_channel=self._origin_channel.get(),
            origin_chat_id=self._origin_chat_id.get(),
            session_key=self._session_key.get(),
            context_from=context_from if isinstance(context_from, str) else None,
        )
