from __future__ import annotations

import asyncio
from typing import Any, cast

from loguru import logger

from bao.agent import plan as plan_state
from bao.agent._loop_run_models import RunAgentLoopOptions
from bao.agent._loop_turn_output_models import (
    ControlOutboundRequest,
    ExecuteTurnLoopRequest,
    PersistAssistantTurnRequest,
)
from bao.agent._loop_types import TurnExecutionOutcome as _TurnExecutionOutcome
from bao.bus.events import InboundMessage, OutboundMessage
from bao.progress_scope import main_progress_scope
from bao.session.manager import Session
from bao.utils.attachments import attachment_file_paths, persist_attachment_records


class LoopTurnOutputMixin:
    def _current_plan_signal_text(self, session: Session) -> str:
        return plan_state.plan_signal_text(session.metadata.get(plan_state.PLAN_STATE_KEY))

    async def _execute_turn_loop(self, request: ExecuteTurnLoopRequest) -> _TurnExecutionOutcome:
        run_result = await self._run_agent_loop(
            request.initial_messages,
            options=RunAgentLoopOptions(
                on_progress=request.on_progress,
                on_tool_hint=request.on_tool_hint,
                artifact_session_key=request.session.key,
                return_interrupt=True,
                tool_signal_text=self._current_plan_signal_text(request.session),
                on_event=request.on_event,
                on_visible_assistant_turn=request.on_visible_assistant_turn,
                tool_hint_lang=request.session_lang,
            ),
        )
        parsed_result = self._unpack_process_message_run_result(cast(tuple[Any, ...], run_result))
        final_content = parsed_result.final_content
        if not isinstance(final_content, str) or not final_content.strip():
            final_content = request.fallback_text_fn(
                request.session_lang,
                bool(parsed_result.reply_attachments),
            )
        return _TurnExecutionOutcome(parsed_result=parsed_result, final_content=final_content)

    async def _persist_assistant_turn(self, request: PersistAssistantTurnRequest) -> None:
        if request.final_content or request.tools_used or request.reply_attachments:
            request.session.add_message(
                "assistant",
                request.final_content,
                tools_used=request.tools_used if request.tools_used else None,
                status=request.assistant_status,
                attachments=persist_attachment_records(request.reply_attachments),
                references=dict(request.references or {}),
            )
        await asyncio.to_thread(self.sessions.save, request.session)
        if (
            not request.session.metadata.get("title")
            and request.session.key not in self._title_generation_inflight
        ):
            self._title_generation_inflight.add(request.session.key)

            async def _generate_and_clear_title() -> None:
                try:
                    await self._generate_session_title(request.session)
                finally:
                    self._title_generation_inflight.discard(request.session.key)

            asyncio.create_task(_generate_and_clear_title())

    async def _persist_display_only_assistant_turn(self, *, session: Session, content: str, source: str = "assistant-progress") -> None:
        visible_text = (self._strip_think(content) or "").strip()
        if not visible_text:
            return
        last_message = session.messages[-1] if session.messages else None
        if isinstance(last_message, dict) and last_message.get("role") == "assistant" and last_message.get("content") == visible_text and last_message.get("_source") == source:
            return
        session.add_message("assistant", visible_text, status="done", _source=source)
        await asyncio.to_thread(self.sessions.save, session)

    async def _set_session_running_metadata(self, key: str, is_running: bool) -> None:
        try:
            await asyncio.to_thread(self.sessions.set_session_running, key, bool(is_running))
        except Exception as exc:
            logger.debug("Skip session running metadata update {}: {}", key, exc)

    def _tool_hints_enabled(self) -> bool:
        defaults = getattr(getattr(self._config, "agents", None), "defaults", None)
        return True if defaults is None else bool(getattr(defaults, "send_tool_hints", True))

    def _prepare_outbound_metadata(self, metadata: dict[str, Any] | None = None, *, session_key: str | None = None) -> tuple[dict[str, Any], str | None]:
        out_meta = dict(metadata or {})
        if session_key:
            out_meta["session_key"] = session_key
        reply_to = out_meta.get("reply_to") if isinstance(out_meta.get("reply_to"), str) else None
        if any(self._last_tool_budget.values()):
            out_meta["_tool_budget"] = dict(self._last_tool_budget)
        if self._last_tool_observability:
            out_meta["_tool_observability"] = dict(self._last_tool_observability)
        return out_meta, reply_to

    def _build_user_outbound_message(self, msg: InboundMessage, final_content: str, *, reply_attachments: list[dict[str, Any]] | None = None) -> OutboundMessage:
        out_meta, reply_to = self._prepare_outbound_metadata(msg.metadata)
        out_meta["_progress_scope"] = main_progress_scope(
            channel=msg.channel,
            chat_id=msg.chat_id,
            metadata=out_meta,
        )
        return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=final_content, reply_to=reply_to, media=attachment_file_paths(reply_attachments), metadata=out_meta)

    def _build_control_outbound_message(self, request: ControlOutboundRequest) -> OutboundMessage:
        out_meta, reply_to = self._prepare_outbound_metadata(
            request.metadata,
            session_key=request.session_key,
        )
        return OutboundMessage(
            channel=request.channel,
            chat_id=request.chat_id,
            content=request.final_content,
            reply_to=reply_to,
            media=attachment_file_paths(request.reply_attachments),
            metadata=out_meta,
        )

    async def _clear_progress_buffer(self, *, channel: str, chat_id: str, metadata: dict[str, Any] | None = None) -> None:
        await self.bus.publish_outbound(OutboundMessage(channel=channel, chat_id=chat_id, content="", metadata={**(metadata or {}), "_progress": True, "_progress_clear": True}))
