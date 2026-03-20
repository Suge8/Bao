from __future__ import annotations

import asyncio

from loguru import logger

from bao.agent import shared
from bao.bus.events import ControlEvent, OutboundMessage
from bao.progress_scope import subagent_progress_scope

from ._subagent_status_runtime import ChildResultRequest
from ._subagent_types import AnnounceResultRequest, RunRequest, StatusUpdate


class _SubagentRunNotifyMixin:
    async def _announce_result_non_fatal(self, request: AnnounceResultRequest) -> None:
        try:
            await self._announce_result(request)
        except asyncio.CancelledError:
            logger.debug("Subagent [{}] announce cancelled (non-fatal)", request.task_id)
        except Exception as exc:
            logger.debug("Subagent [{}] announce failed (non-fatal): {}", request.task_id, exc)

    async def _announce_result(self, request: AnnounceResultRequest) -> None:
        await self.bus.publish_outbound(
            OutboundMessage(
                channel=request.origin["channel"],
                chat_id=request.origin["chat_id"],
                content="",
                metadata={
                    "_progress": True,
                    "_progress_clear": True,
                    "_subagent_progress": True,
                    "_progress_scope": subagent_progress_scope(request.task_id),
                    "task_id": request.task_id,
                },
            )
        )
        event = ControlEvent(
            kind=shared.SUBAGENT_RESULT_EVENT_TYPE,
            payload=shared.build_subagent_result_event(
                shared.SubagentResultEventRequest(
                    task_id=request.task_id,
                    label=self._sanitize_visible(request.label),
                    task=self._sanitize_visible(request.task),
                    status=request.status,
                    result=self._sanitize_visible(request.result),
                )
            ),
            session_key=request.origin.get("session_key", ""),
            origin_channel=request.origin["channel"],
            origin_chat_id=request.origin["chat_id"],
            source="subagent",
        )
        await self.bus.publish_control(event)
        logger.debug(
            "Subagent [{}] announced result to {}:{}",
            request.task_id,
            request.origin["channel"],
            request.origin["chat_id"],
        )

    def _persist_child_status(
        self,
        *,
        task_id: str,
        label: str,
        origin: dict[str, str],
        result: str,
        status: str,
    ) -> None:
        child_session_key = origin.get("child_session_key")
        parent_session_key = origin.get("session_key")
        if child_session_key and parent_session_key:
            self._persist_child_result(
                ChildResultRequest(
                    child_session_key=child_session_key,
                    parent_session_key=parent_session_key,
                    label=label,
                    task_id=task_id,
                    result=result,
                    status=status,
                )
            )

    def _persist_child_user_turn_if_needed(self, request: RunRequest) -> None:
        child_session_key = request.origin.get("child_session_key")
        parent_session_key = request.origin.get("session_key")
        if child_session_key and parent_session_key:
            self._persist_child_user_turn(
                child_session_key,
                parent_session_key=parent_session_key,
                label=request.label,
                task_id=request.task_id,
                task=request.task,
            )

    def _mark_interrupted(self, task_id: str) -> None:
        self._update_status(StatusUpdate(task_id=task_id, status="cancelled", phase="cancelled"))

    def _mark_cancelled(self, request: RunRequest) -> None:
        self._mark_interrupted(request.task_id)
        self._persist_child_status(
            task_id=request.task_id,
            label=request.label,
            origin=request.origin,
            result="Cancelled by user.",
            status="cancelled",
        )
        logger.info("👋 子代终止 / subagent stopped: [{}]", request.task_id)
