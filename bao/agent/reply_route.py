from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from bao.agent.reply_route_models import ReplyRouteInput


def _clean_str(value: object, *, lower: bool = False) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    return text.lower() if lower else text


def _clean_optional_id(value: object) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    return text or None


def normalize_reply_metadata(reply_metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(reply_metadata, dict):
        return {}
    slack_meta = reply_metadata.get("slack")
    if not isinstance(slack_meta, dict):
        return {}
    thread_ts = _clean_str(slack_meta.get("thread_ts"))
    if not thread_ts:
        return {}
    normalized_slack: dict[str, Any] = {"thread_ts": thread_ts}
    channel_type = _clean_str(slack_meta.get("channel_type"))
    if channel_type:
        normalized_slack["channel_type"] = channel_type
    return {"slack": normalized_slack}


@dataclass(frozen=True)
class ReplyRoute:
    channel: str = ""
    chat_id: str = ""
    session_key: str = ""
    lang: str = "en"
    message_id: str | None = None
    reply_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, request: ReplyRouteInput) -> "ReplyRoute":
        normalized_channel = _clean_str(request.channel, lower=True)
        normalized_chat_id = _clean_str(request.chat_id)
        normalized_message_id = _clean_optional_id(request.message_id)
        normalized_session_key = (
            _clean_str(request.session_key)
            or (
                f"{normalized_channel}:{normalized_chat_id}"
                if normalized_channel and normalized_chat_id
                else ""
            )
        )
        normalized_lang = _clean_str(request.lang, lower=True) or "en"
        return cls(
            channel=normalized_channel,
            chat_id=normalized_chat_id,
            session_key=normalized_session_key,
            lang=normalized_lang,
            message_id=normalized_message_id,
            reply_metadata=normalize_reply_metadata(request.reply_metadata),
        )


class TurnContextStore:
    def __init__(self, key: str, default_route: ReplyRouteInput | None = None) -> None:
        self._route_ctx: ContextVar[ReplyRoute] = ContextVar(
            key,
            default=ReplyRoute.create(default_route or ReplyRouteInput()),
        )

    def set(self, route: ReplyRouteInput) -> None:
        self._route_ctx.set(ReplyRoute.create(route))

    def get(self) -> ReplyRoute:
        return self._route_ctx.get()
