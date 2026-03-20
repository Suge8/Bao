from __future__ import annotations

from collections.abc import Iterable

from bao.agent._loop_user_message_models import ProcessDirectRequest
from bao.bus.events import ControlEvent, InboundMessage

from ._route_resolution import SessionOrigin


def dispatch_session_key(msg: InboundMessage) -> str:
    override = msg.metadata.get("session_key")
    if isinstance(override, str) and override:
        return override
    if msg.channel == "system":
        if ":" in msg.chat_id:
            origin_channel, origin_chat_id = msg.chat_id.split(":", 1)
            return f"{origin_channel}:{origin_chat_id}"
        return f"hub:{msg.chat_id}"
    return msg.session_key


def dispatch_control_session_key(event: ControlEvent) -> str:
    session_key = event.session_key.strip()
    if session_key:
        return session_key
    channel = event.origin_channel.strip() or "hub"
    chat_id = event.origin_chat_id.strip() or "direct"
    return f"{channel}:{chat_id}"


def origin_from_message(msg: InboundMessage) -> SessionOrigin:
    channel = msg.channel
    chat_id = msg.chat_id
    if channel == "system" and ":" in chat_id:
        channel, chat_id = chat_id.split(":", 1)
    return SessionOrigin.create(channel=channel, chat_id=chat_id, metadata=msg.metadata)


def origin_from_control_event(event: ControlEvent) -> SessionOrigin:
    payload = dict(event.payload) if isinstance(event.payload, dict) else {}
    payload.update(dict(event.metadata))
    return SessionOrigin.create(
        channel=event.origin_channel,
        chat_id=event.origin_chat_id,
        metadata=payload,
    )


def origin_from_request(request: ProcessDirectRequest) -> SessionOrigin:
    return SessionOrigin.create(
        channel=request.channel,
        chat_id=request.chat_id,
        metadata=request.metadata,
    )


def normalize_profile_id(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def normalize_profile_ids(values: Iterable[object]) -> tuple[str, ...]:
    normalized = [normalize_profile_id(item) for item in values]
    return tuple(item for item in normalized if item)
