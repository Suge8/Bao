"""Spawn tool for creating background subagents."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from loguru import logger

from bao.agent import plan
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
        self._origin_channel: ContextVar[str] = ContextVar(
            "spawn_origin_channel", default="gateway"
        )
        self._origin_chat_id: ContextVar[str] = ContextVar("spawn_origin_chat_id", default="direct")
        self._lang: ContextVar[str] = ContextVar("spawn_lang", default="en")
        self._reply_metadata: ContextVar[dict[str, Any]] = ContextVar(
            "spawn_reply_metadata", default={}
        )
        self._session_key: ContextVar[str] = ContextVar(
            "spawn_session_key", default="gateway:direct"
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
        self._origin_channel.set(channel)
        self._origin_chat_id.set(chat_id)
        self._lang.set(plan.normalize_language(lang))
        self._reply_metadata.set(self._normalize_reply_metadata(reply_metadata))
        self._session_key.set(session_key or f"{channel}:{chat_id}")

    @staticmethod
    def _normalize_reply_metadata(reply_metadata: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(reply_metadata, dict):
            return {}
        slack_meta = reply_metadata.get("slack")
        if not isinstance(slack_meta, dict):
            return {}
        thread_ts = slack_meta.get("thread_ts")
        if not isinstance(thread_ts, str) or not thread_ts.strip():
            return {}
        normalized_slack: dict[str, Any] = {"thread_ts": thread_ts}
        channel_type = slack_meta.get("channel_type")
        if isinstance(channel_type, str) and channel_type.strip():
            normalized_slack["channel_type"] = channel_type
        return {"slack": normalized_slack}

    def _spawn_notice_text(self) -> str:
        if plan.normalize_language(self._lang.get()) == "zh":
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

        metadata = dict(self._reply_metadata.get() or {})
        metadata.update(
            {
                "_subagent_spawn": result.to_payload(),
                "session_key": self._session_key.get(),
            }
        )

        await self._publish_outbound(
            OutboundMessage(
                channel=self._origin_channel.get(),
                chat_id=self._origin_chat_id.get(),
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
            "origin_channel": self._origin_channel.get(),
            "origin_chat_id": self._origin_chat_id.get(),
            "session_key": self._session_key.get(),
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
