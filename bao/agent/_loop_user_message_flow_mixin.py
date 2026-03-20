from __future__ import annotations

import asyncio
from typing import Any, cast

from loguru import logger

from bao.agent._loop_agent_support_mixin import ExperienceLearningRequest
from bao.agent._loop_tool_setup import ToolContextRequest
from bao.agent._loop_turn_output_models import ExecuteTurnLoopRequest, PersistAssistantTurnRequest
from bao.agent._loop_types import extract_text as _extract_text
from bao.agent._loop_user_message_models import (
    FinalizeUserTurnRequest,
    ProcessedMessageContext,
    ProcessMessageOptions,
    UserTurnRequest,
)
from bao.bus.events import InboundMessage, OutboundMessage
from bao.progress_scope import main_progress_scope, tool_progress_scope
from bao.providers.retry import PROGRESS_RESET

from ._loop_user_message_setup_mixin import ReplyFlowError


class LoopUserMessageFlowMixin:
    async def _process_message(
        self,
        msg: InboundMessage,
        options: ProcessMessageOptions | None = None,
    ) -> OutboundMessage | None:
        if msg.channel == "system":
            return await self._process_system_message(msg)
        options = options or ProcessMessageOptions()
        context = await self._prepare_user_message_context(msg, options)
        return await self._process_user_message_context(context, options)

    async def _prepare_user_message_context(
        self,
        msg: InboundMessage,
        options: ProcessMessageOptions,
    ) -> ProcessedMessageContext:
        if not msg.metadata.get("_ephemeral"):
            preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
            logger.info("📨 收到消息 / in: {}:{}: {}", msg.channel, msg.sender_id, preview)
        await self._cleanup_stale_artifacts_if_needed()
        natural_key = options.session_key or msg.session_key
        key = self.sessions.get_active_session_key(natural_key) or natural_key
        session = self.sessions.get_or_create(key)
        track_running = msg.channel != "desktop" and not msg.metadata.get("_ephemeral")
        return ProcessedMessageContext(
            msg=msg,
            session=session,
            session_key=key,
            natural_key=natural_key,
            track_running=track_running,
        )

    async def _process_user_message_context(
        self,
        context: ProcessedMessageContext,
        options: ProcessMessageOptions,
    ) -> OutboundMessage | None:
        msg = context.msg
        session = context.session
        key = context.session_key
        track_running = context.track_running
        if track_running and session.metadata.get("session_running") is not True:
            await self._set_session_running_metadata(session.key, True)
        try:
            command_response = await self._handle_user_command(msg, session, context.natural_key)
            if command_response is not None:
                return command_response
            try:
                msg = await self._apply_onboarding_if_needed(msg, session)
            except ReplyFlowError as exc:
                return exc.response
            session_lang, recall, initial_messages = await self._prepare_user_turn_inputs(
                msg=msg,
                session=session,
                session_key=key,
            )
            execution = await self._run_user_turn(
                UserTurnRequest(
                    msg=msg,
                    session=session,
                    session_lang=session_lang,
                    initial_messages=initial_messages,
                    on_progress=options.on_progress,
                    on_event=options.on_event,
                )
            )
            if execution is None:
                return None
            parsed_result, final_content = execution
            return await self._finalize_user_turn(
                FinalizeUserTurnRequest(
                    msg=msg,
                    session=session,
                    session_key=key,
                    recall=cast(dict[str, Any], recall),
                    parsed_result=parsed_result,
                    final_content=final_content,
                    expected_generation=options.expected_generation,
                    expected_generation_key=options.expected_generation_key,
                )
            )
        finally:
            if track_running:
                await self._set_session_running_metadata(session.key, False)

    async def _prepare_user_turn_inputs(
        self,
        *,
        msg: InboundMessage,
        session,
        session_key: str,
    ) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        self._schedule_memory_consolidation_if_needed(session)
        session_lang, lang_changed = self._resolve_session_language(session, _extract_text(msg.content))
        if lang_changed and not msg.metadata.get("_ephemeral"):
            await asyncio.to_thread(self.sessions.save, session)
        self._set_tool_context(
            ToolContextRequest(
                channel=msg.channel,
                chat_id=msg.chat_id,
                session_key=session_key,
                lang=session_lang,
                metadata=msg.metadata,
            )
        )
        recall = await self._recall_context_for_query(msg.content)
        initial_messages = self._build_initial_messages_for_user_turn(session, msg, recall=recall)
        if not msg.metadata.get("_pre_saved") and not msg.metadata.get("_ephemeral"):
            save_kwargs: dict[str, Any] = {}
            token = msg.metadata.get("_pre_saved_token")
            if isinstance(token, str) and token:
                save_kwargs["status"] = "pending"
                save_kwargs["_pre_saved_token"] = token
            session.add_message("user", msg.content, **save_kwargs)
            await asyncio.to_thread(self.sessions.save, session)
        return session_lang, cast(dict[str, Any], recall), initial_messages

    async def _finalize_user_turn(
        self,
        request: FinalizeUserTurnRequest,
    ) -> OutboundMessage | None:
        generation_key = request.expected_generation_key or request.msg.session_key
        if self._is_stale_generation(
            request.expected_generation,
            generation_key,
            "Suppressing stale completion before persistence for session {}",
        ):
            return None
        assistant_status = "error" if request.parsed_result.provider_error else "done"
        if self._is_stale_generation(
            request.expected_generation,
            generation_key,
            "Suppressing stale side-effects before persistence for session {}",
        ):
            return None
        self._maybe_learn_experience(
            request=ExperienceLearningRequest(
                session=request.session,
                user_request=request.msg.content,
                final_response=request.final_content,
                tools_used=request.parsed_result.tools_used,
                tool_trace=request.parsed_result.tool_trace,
                total_errors=request.parsed_result.total_errors,
                reasoning_snippets=request.parsed_result.reasoning_snippets,
            )
        )
        self._persist_tool_observability(
            request.session,
            channel=request.msg.channel,
            session_key=request.session_key,
        )
        await self._persist_assistant_turn(
            PersistAssistantTurnRequest(
                session=request.session,
                final_content=request.final_content,
                tools_used=request.parsed_result.tools_used,
                assistant_status=assistant_status,
                reply_attachments=request.parsed_result.reply_attachments,
                references=cast(dict[str, Any], request.recall.get("references") or {}),
            )
        )
        preview = (
            request.final_content[:120] + "..."
            if len(request.final_content) > 120
            else request.final_content
        )
        logger.info(
            "💬 回复消息 / out: {}:{}: {}",
            request.msg.channel,
            request.msg.sender_id,
            preview,
        )
        return self._build_user_outbound_message(
            request.msg,
            request.final_content,
            reply_attachments=request.parsed_result.reply_attachments,
        )

    async def _run_user_turn(self, request: UserTurnRequest) -> tuple[Any, str] | None:
        async def _bus_publish(content: str, *, is_tool_hint: bool = False) -> None:
            if content == PROGRESS_RESET and not is_tool_hint:
                return
            meta = dict(request.msg.metadata or {})
            meta["_progress"] = True
            if is_tool_hint:
                logger.debug("Tool hint sent to {}:{}: {}", request.msg.channel, request.msg.chat_id, content)
                meta["_tool_hint"] = True
                meta["_progress_scope"] = tool_progress_scope(
                    channel=request.msg.channel,
                    chat_id=request.msg.chat_id,
                    metadata=meta,
                )
            else:
                meta["_progress_scope"] = main_progress_scope(
                    channel=request.msg.channel,
                    chat_id=request.msg.chat_id,
                    metadata=meta,
                )
            await self.bus.publish_outbound(OutboundMessage(channel=request.msg.channel, chat_id=request.msg.chat_id, content=content, metadata=meta))

        async def _persist_visible_assistant_turn(content: str) -> None:
            await self._persist_display_only_assistant_turn(session=request.session, content=content)

        execution = await self._execute_turn_loop(
            ExecuteTurnLoopRequest(
                initial_messages=request.initial_messages,
                session=request.session,
                session_lang=request.session_lang,
                fallback_text_fn=self._reply_fallback_text,
                on_progress=request.on_progress or _bus_publish,
                on_tool_hint=lambda c: _bus_publish(c, is_tool_hint=True),
                on_event=request.on_event,
                on_visible_assistant_turn=_persist_visible_assistant_turn,
            )
        )
        parsed_result = execution.parsed_result
        if parsed_result.interrupted:
            self._handle_interrupted_process_message(
                request.session,
                request.msg,
                completed_tool_msgs=parsed_result.completed_tool_msgs,
            )
            return None
        return parsed_result, execution.final_content
