from __future__ import annotations

import asyncio
from typing import Any

from bao.agent._loop_types import BackgroundTurnInput
from bao.agent._loop_user_message_models import ProcessDirectRequest
from bao.agent._session_handoff import (
    SESSION_HANDOFF_HINT_SOURCE,
    SESSION_HANDOFF_RESULT_EVENT_TYPE,
    SessionHandoffResult,
    build_source_result_hint,
    build_source_result_prompt,
    build_source_send_hint,
    build_target_receive_hint,
)
from bao.bus.events import ControlEvent, OutboundMessage


def build_background_turn_from_session_handoff_result(
    *,
    payload: Any,
    session_key: str,
    origin_channel: str,
    origin_chat_id: str,
    metadata: dict[str, Any] | None = None,
) -> BackgroundTurnInput:
    return BackgroundTurnInput(
        session_key=session_key,
        origin_channel=origin_channel,
        origin_chat_id=origin_chat_id,
        system_prompt_text=build_source_result_prompt(payload),
        search_query=payload.request_content,
        metadata=dict(metadata or {}),
    )


async def process_session_handoff_request_event(loop: Any, request: Any) -> None:
    await emit_session_handoff_hint(
        loop,
        session_key=request.source_session_key,
        channel=request.source_channel,
        chat_id=request.source_chat_id,
        metadata=request.source_metadata,
        content=build_source_send_hint(
            target_channel=request.target_channel,
            target_label=request.target_label,
            request_content=request.content,
            has_media=bool(request.media),
            lang=session_language_for_key(loop, request.source_session_key),
        ),
    )
    await emit_session_handoff_hint(
        loop,
        session_key=request.target_session_key,
        channel=request.target_channel,
        chat_id=request.target_chat_id,
        metadata=request.target_metadata,
        content=build_target_receive_hint(
            source_channel=request.source_channel,
            source_label=request.source_label,
            request_content=request.content,
            has_media=bool(request.media),
            lang=session_language_for_key(loop, request.target_session_key),
        ),
    )
    result_text, status = await _run_target_handoff(loop, request)
    await loop.bus.publish_control(
        ControlEvent(
            kind=SESSION_HANDOFF_RESULT_EVENT_TYPE,
            payload=SessionHandoffResult(
                handoff_id=request.handoff_id,
                source_session_key=request.source_session_key,
                source_channel=request.source_channel,
                source_chat_id=request.source_chat_id,
                source_metadata=dict(request.source_metadata),
                source_label=request.source_label,
                target_session_key=request.target_session_key,
                target_channel=request.target_channel,
                target_label=request.target_label,
                request_content=request.content,
                status=status,
                result=result_text,
            ).as_payload(),
            session_key=request.source_session_key,
            origin_channel=request.source_channel,
            origin_chat_id=request.source_chat_id,
            source="session_handoff",
        )
    )


async def process_session_handoff_result_event(loop: Any, result: Any) -> OutboundMessage | None:
    await emit_session_handoff_hint(
        loop,
        session_key=result.source_session_key,
        channel=result.source_channel,
        chat_id=result.source_chat_id,
        metadata=result.source_metadata,
        content=build_source_result_hint(
            target_channel=result.target_channel,
            target_label=result.target_label,
            result_content=result.result,
            lang=session_language_for_key(loop, result.source_session_key),
        ),
    )
    return await loop._execute_background_turn(
        build_background_turn_from_session_handoff_result(
            payload=result,
            session_key=result.source_session_key,
            origin_channel=result.source_channel,
            origin_chat_id=result.source_chat_id,
            metadata=result.source_metadata,
        )
    )


async def emit_session_handoff_hint(
    loop: Any,
    *,
    session_key: str,
    channel: str,
    chat_id: str,
    metadata: dict[str, Any] | None,
    content: str,
) -> None:
    if not content:
        return
    session = loop.sessions.get_or_create(session_key)
    await loop._persist_display_only_assistant_turn(
        session=session,
        content=content,
        source=SESSION_HANDOFF_HINT_SOURCE,
    )
    if not channel or not chat_id:
        return
    outbound = OutboundMessage(
        channel=channel,
        chat_id=chat_id,
        content=content,
        metadata={"session_key": session_key, **dict(metadata or {})},
    )
    sender = getattr(loop, "_delivery_sender", None)
    if callable(sender):
        await sender(outbound)
        return
    await loop.bus.publish_outbound(outbound)


def session_language_for_key(loop: Any, session_key: str) -> str:
    session = loop.sessions.get_or_create(session_key)
    session_lang, lang_changed = loop._resolve_session_language(session)
    if lang_changed:
        loop.sessions.save(session)
    return session_lang


async def _run_target_handoff(loop: Any, request: Any) -> tuple[str, str]:
    try:
        result_text = await loop.process_direct(
            ProcessDirectRequest(
                content=request.content,
                session_key=request.target_session_key,
                channel=request.target_channel or "hub",
                chat_id=request.target_chat_id or "direct",
                media=list(request.media),
                metadata={
                    **dict(request.target_metadata),
                    "_session_handoff": True,
                    "handoff_id": request.handoff_id,
                    "source_session_key": request.source_session_key,
                },
            )
        )
        return result_text, "ok"
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return f"Error: {exc}", "error"
