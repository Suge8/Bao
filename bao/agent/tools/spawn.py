"""Spawn tool for creating background subagents."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from loguru import logger

from bao.agent import plan
from bao.agent.reply_route import TurnContextStore
from bao.agent.subagent import SpawnResult
from bao.agent.tools.base import Tool
from bao.bus.events import OutboundMessage

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
        self._publish_outbound: Callable[[OutboundMessage], Awaitable[None]] | None = None
        self._route = TurnContextStore(
            "spawn_route",
            channel="gateway",
            chat_id="direct",
            session_key="gateway:direct",
        )

    def set_publish_outbound(
        self, publish_outbound: Callable[[OutboundMessage], Awaitable[None]] | None
    ) -> None:
        self._publish_outbound = publish_outbound

    def set_context(
        self,
        channel: str,
        chat_id: str,
        session_key: str | None = None,
        lang: str | None = None,
        reply_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Set the origin context for subagent announcements."""
        self._route.set(
            channel=channel,
            chat_id=chat_id,
            session_key=session_key or f"{channel}:{chat_id}",
            lang=plan.normalize_language(lang),
            reply_metadata=reply_metadata,
        )

    def _spawn_notice_text(self) -> str:
        if plan.normalize_language(self._route.get().lang) == "zh":
            return "已委派子代理处理中，完成后我会同步结果。"
        return "I've delegated this to a subagent and will share the result once it's done."

    @staticmethod
    def _serialize_result(result: SpawnResult) -> str:
        return json.dumps(result.to_payload(), ensure_ascii=False)

    async def _notify_spawn_started(self, result: "SpawnResult") -> None:
        if not self._publish_outbound:
            return
        if result.status != "spawned" or result.task is None:
            return

        route = self._route.get()
        metadata = dict(route.reply_metadata)
        metadata.update(
            {
                "_subagent_spawn": result.to_payload(),
                "session_key": route.session_key,
            }
        )

        await self._publish_outbound(
            OutboundMessage(
                channel=route.channel,
                chat_id=route.chat_id,
                content=self._spawn_notice_text(),
                metadata=metadata,
            )
        )

    @property
    def name(self) -> str:
        return "spawn"

    @property
    def description(self) -> str:
        return (
            "Delegate a task to a background subagent. Returns schema_version=1 JSON; "
            "query progress with task.task_id."
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
                "child_session_key": {
                    "type": "string",
                    "description": "Optional child session key to continue an existing subagent thread",
                },
            },
            "required": ["task"],
        }

    async def execute(self, **kwargs: Any) -> str:
        """Spawn a subagent to execute the given task."""
        task = kwargs.get("task")
        label = kwargs.get("label")
        context_from = kwargs.get("context_from")
        child_session_key = kwargs.get("child_session_key")
        if not isinstance(task, str) or not task:
            return self._serialize_result(
                SpawnResult.failed(code="task_required", message="task text is required")
            )
        if label is not None and not isinstance(label, str):
            return self._serialize_result(
                SpawnResult.failed(code="invalid_label", message="label must be a string")
            )
        spawn_kwargs: dict[str, Any] = {
            "task": task,
            "label": label,
            "origin_channel": self._route.get().channel,
            "origin_chat_id": self._route.get().chat_id,
            "session_key": self._route.get().session_key,
            "context_from": context_from if isinstance(context_from, str) else None,
        }
        if isinstance(child_session_key, str):
            spawn_kwargs["child_session_key"] = child_session_key
        result = await self._manager.spawn(**spawn_kwargs)
        try:
            await self._notify_spawn_started(result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Spawn notify failed (non-fatal): {}", exc)
        return self._serialize_result(result)
