from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from bao.agent import plan
from bao.agent.reply_route import TurnContextStore
from bao.agent.reply_route_models import ReplyRouteInput
from bao.agent.tools.base import Tool
from bao.bus.events import OutboundMessage
from bao.session.manager import SessionManager


class _PlanToolBase:
    def __init__(
        self,
        sessions: SessionManager,
        publish_outbound: Callable[[OutboundMessage], Awaitable[None]] | None = None,
    ):
        self._sessions = sessions
        self._publish_outbound = publish_outbound
        self._route = TurnContextStore(
            "plan_route",
            ReplyRouteInput(
                channel="hub",
                chat_id="direct",
                session_key="hub:direct",
            ),
        )

    def set_context(
        self,
        channel: str,
        chat_id: str,
        session_key: str | None = None,
        lang: str | None = None,
        reply_metadata: dict[str, Any] | None = None,
    ) -> None:
        self._route.set(
            ReplyRouteInput(
                channel=channel,
                chat_id=chat_id,
                session_key=session_key or f"{channel}:{chat_id}",
                lang=plan.normalize_language(lang),
                reply_metadata=dict(reply_metadata or {}),
            ),
        )

    def _get_session_key(self) -> str:
        key = self._route.get().session_key.strip()
        if key:
            return key
        route = self._route.get()
        return f"{route.channel}:{route.chat_id}"

    def _get_language(self) -> str:
        return plan.normalize_language(self._route.get().lang)

    async def _notify_user(self, content: str, *, action: str) -> None:
        if not self._publish_outbound or not content.strip():
            return
        try:
            route = self._route.get()
            payload = dict(route.reply_metadata)
            payload.update(
                {
                    "_plan": True,
                    "plan_action": action,
                    "session_key": self._get_session_key(),
                }
            )
            await self._publish_outbound(
                OutboundMessage(
                    channel=route.channel,
                    chat_id=route.chat_id,
                    content=content,
                    metadata=payload,
                )
            )
        except Exception as exc:
            logger.warning(
                "⚠️ 计划通知发送失败 / plan notify failed: action={} channel={} chat_id={} session={} err={}",
                action,
                route.channel,
                route.chat_id,
                self._get_session_key(),
                exc,
            )
            return


class CreatePlanTool(_PlanToolBase, Tool):
    @property
    def name(self) -> str:
        return "create_plan"

    @property
    def description(self) -> str:
        return "Create a plan with goal and steps, replacing any active plan."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "The overall goal of the plan."},
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered step list, ideally 2-10 items.",
                },
            },
            "required": ["goal", "steps"],
        }

    async def execute(self, **kwargs: Any) -> str:
        goal = kwargs.get("goal")
        steps = kwargs.get("steps")
        if not isinstance(goal, str) or not goal.strip():
            return "Error: goal is required"
        if not isinstance(steps, list) or not steps:
            return "Error: steps must be a non-empty list"
        if not all(isinstance(step, str) and step.strip() for step in steps):
            return "Error: each step must be a non-empty string"

        state = plan.new_plan(goal, steps)
        if not state.get("steps"):
            return "Error: no valid steps after normalization"

        session = self._sessions.get_or_create(self._get_session_key())
        session.metadata[plan.PLAN_STATE_KEY] = state
        session.metadata.pop(plan.PLAN_ARCHIVED_KEY, None)
        self._sessions.save(session)
        notify_text = plan.format_plan_for_channel(
            state,
            lang=self._get_language(),
            channel=self._route.get().channel,
        )
        await self._notify_user(
            notify_text,
            action="create",
        )

        total = len(state["steps"])
        return f"Plan created: 0/{total} done; current_step={state['current_step']}"


class UpdatePlanStepTool(_PlanToolBase, Tool):
    @property
    def name(self) -> str:
        return "update_plan_step"

    @property
    def description(self) -> str:
        return "Update one plan step status and advance current_step."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "step_index": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "1-based index of the step to update.",
                },
                "status": {
                    "type": "string",
                    "enum": list(plan.UPDATEABLE_STATUSES),
                    "description": "New status for the step.",
                },
            },
            "required": ["step_index", "status"],
        }

    async def execute(self, **kwargs: Any) -> str:
        step_index = kwargs.get("step_index")
        status = kwargs.get("status")
        if isinstance(step_index, bool):
            return "Error: step_index must be an integer"
        if isinstance(step_index, str) and step_index.strip().isdigit():
            step_index = int(step_index.strip())
        elif isinstance(step_index, float) and step_index.is_integer():
            step_index = int(step_index)
        if not isinstance(step_index, int):
            return "Error: step_index must be an integer"
        if not isinstance(status, str):
            return "Error: status must be a string"
        status = status.strip().lower()
        if status not in plan.UPDATEABLE_STATUSES:
            allowed = ", ".join(plan.UPDATEABLE_STATUSES)
            return f"Error: status must be one of: {allowed}"

        session = self._sessions.get_or_create(self._get_session_key())
        state = session.metadata.get(plan.PLAN_STATE_KEY)
        if not isinstance(state, dict):
            return "Error: no active plan"

        current_status = plan.get_step_status(state, step_index)
        if current_status == status:
            return f"Plan unchanged: step {step_index} already {status}"

        try:
            new_state = plan.set_step_status(state, step_index=step_index, status=status)
        except ValueError as exc:
            return f"Error: {exc}"

        session.metadata[plan.PLAN_STATE_KEY] = new_state
        archived = ""
        archived_for_notify = ""
        if plan.is_plan_done(new_state):
            archived = plan.archive_plan(new_state, lang=self._get_language())
            archived_for_notify = plan.archive_plan_for_channel(
                new_state,
                lang=self._get_language(),
                channel=self._route.get().channel,
            )
            if archived:
                session.metadata[plan.PLAN_ARCHIVED_KEY] = archived
        self._sessions.save(session)

        notify_text = plan.format_plan_for_channel(
            new_state,
            lang=self._get_language(),
            channel=self._route.get().channel,
        )
        if archived_for_notify:
            notify_text = f"{notify_text}\n{archived_for_notify}"
        await self._notify_user(notify_text, action="update")

        done_count = plan.count_status(new_state, plan.STATUS_DONE)
        total = len(new_state["steps"])
        if archived:
            return (
                f"Plan updated: {done_count}/{total} done; current_step={new_state['current_step']}. "
                f"Archived: {archived}"
            )
        return f"Plan updated: {done_count}/{total} done; current_step={new_state['current_step']}"


class ClearPlanTool(_PlanToolBase, Tool):
    @property
    def name(self) -> str:
        return "clear_plan"

    @property
    def description(self) -> str:
        return "Clear the active plan from session metadata."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> str:
        del kwargs
        session = self._sessions.get_or_create(self._get_session_key())
        had_plan = plan.PLAN_STATE_KEY in session.metadata
        session.metadata.pop(plan.PLAN_STATE_KEY, None)
        archived = session.metadata.get(plan.PLAN_ARCHIVED_KEY)
        self._sessions.save(session)
        if not had_plan:
            return plan.no_plan_to_clear_text(self._get_language())
        archived_text = archived if isinstance(archived, str) else ""
        clear_text = plan.plan_cleared_text(archived_text, lang=self._get_language())
        notify_text = plan.plan_cleared_text_for_channel(
            archived_text,
            lang=self._get_language(),
            channel=self._route.get().channel,
        )
        await self._notify_user(notify_text, action="clear")
        return clear_text
