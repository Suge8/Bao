from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, cast

from bao.agent import plan as plan_state
from bao.agent._loop_tool_context import ToolContextRequest
from bao.agent._loop_turn_output_models import ControlOutboundRequest, ExecuteTurnLoopRequest
from bao.agent.context import BuildMessagesRequest
from bao.bus.events import OutboundMessage


@dataclass(slots=True)
class BackgroundTurnFinalizeRequest:
    session: Any
    session_key: str
    origin_channel: str
    search_query: str
    system_prompt_text: str
    final_content: str
    parsed_result: Any
    references: dict[str, Any] | None = None


async def execute_background_turn(loop: Any, turn_input: Any) -> OutboundMessage | None:
    session = loop.sessions.get_or_create(turn_input.session_key)
    session_lang = await _prepare_background_session(loop, session, turn_input)
    recall = await loop._recall_context_for_query(turn_input.search_query)
    initial_messages = loop.context.build_messages(
        BuildMessagesRequest(
            history=session.get_history(max_messages=loop.memory_window),
            current_message=turn_input.system_prompt_text,
            channel=turn_input.origin_channel,
            chat_id=turn_input.origin_chat_id,
            long_term_memory=str(recall.get("long_term_memory") or ""),
            related_memory=cast(list[Any], recall.get("related_memory") or None),
            related_experience=cast(list[Any], recall.get("related_experience") or None),
            model=loop.model,
            plan_state=session.metadata.get(plan_state.PLAN_STATE_KEY),
        ),
    )
    execution = await loop._execute_turn_loop(
        ExecuteTurnLoopRequest(
            initial_messages=initial_messages,
            session=session,
            session_lang=session_lang,
            fallback_text_fn=loop._background_turn_fallback_text,
        )
    )
    if execution.parsed_result.interrupted:
        return None
    return _build_background_outbound(loop, turn_input, session, execution, recall)


async def _prepare_background_session(loop: Any, session: Any, turn_input: Any) -> str:
    session_lang, lang_changed = loop._resolve_session_language(session)
    if lang_changed:
        await asyncio.to_thread(loop.sessions.save, session)
    loop._set_tool_context(
        ToolContextRequest(
            channel=turn_input.origin_channel,
            chat_id=turn_input.origin_chat_id,
            session_key=turn_input.session_key,
            lang=session_lang,
            metadata=turn_input.metadata,
        )
    )
    return session_lang


def _build_background_outbound(
    loop: Any,
    turn_input: Any,
    session: Any,
    execution: Any,
    recall: dict[str, Any],
) -> OutboundMessage:
    reply_attachments = loop._finalize_background_turn(
        BackgroundTurnFinalizeRequest(
            session=session,
            session_key=turn_input.session_key,
            origin_channel=turn_input.origin_channel,
            search_query=turn_input.search_query,
            system_prompt_text=turn_input.system_prompt_text,
            final_content=execution.final_content,
            parsed_result=execution.parsed_result,
            references=cast(dict[str, Any], recall.get("references") or {}),
        )
    )
    out_meta, _ = loop._prepare_outbound_metadata(
        turn_input.metadata,
        session_key=turn_input.session_key,
    )
    return loop._build_control_outbound_message(
        ControlOutboundRequest(
            channel=turn_input.origin_channel,
            chat_id=turn_input.origin_chat_id,
            session_key=turn_input.session_key,
            final_content=execution.final_content,
            metadata=out_meta,
            reply_attachments=reply_attachments,
        )
    )
