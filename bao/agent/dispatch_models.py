from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Awaitable, Callable

from bao.agent.protocol import StreamEvent
from bao.agent.reply_route import ReplyRoute
from bao.agent.reply_route_models import ReplyRouteInput
from bao.bus.events import InboundMessage


def _clean_profile_id(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


@dataclass(frozen=True, slots=True)
class RouteKey:
    profile_id: str = ""
    session_key: str = ""
    channel: str = ""
    chat_id: str = ""
    reply_target_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        profile_id: object = "",
        session_key: str | None = None,
        channel: str = "",
        chat_id: str = "",
        reply_target_id: str | int | None = None,
    ) -> "RouteKey":
        route = ReplyRoute.create(
            ReplyRouteInput(
                channel=channel,
                chat_id=chat_id,
                session_key=session_key,
                message_id=reply_target_id,
            )
        )
        return cls.from_reply_route(route, profile_id=profile_id)

    @classmethod
    def from_reply_route(cls, route: ReplyRoute, *, profile_id: object = "") -> "RouteKey":
        return cls(
            profile_id=_clean_profile_id(profile_id),
            session_key=route.session_key,
            channel=route.channel,
            chat_id=route.chat_id,
            reply_target_id=route.message_id,
        )


@dataclass(frozen=True, slots=True)
class WakeRequest:
    content: str
    route: RouteKey
    media: tuple[str, ...] = ()
    on_progress: Callable[[str], Awaitable[None]] | None = None
    on_event: Callable[[StreamEvent], Awaitable[None]] | None = None
    ephemeral: bool = False
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    @classmethod
    def create(
        cls,
        *,
        content: str,
        route: RouteKey,
        media: list[str] | tuple[str, ...] | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_event: Callable[[StreamEvent], Awaitable[None]] | None = None,
        ephemeral: bool = False,
        metadata: dict[str, Any] | Mapping[str, Any] | None = None,
    ) -> "WakeRequest":
        normalized_media = tuple(str(item) for item in (media or ()) if isinstance(item, str) and item)
        normalized_metadata = MappingProxyType(dict(metadata or {}))
        return cls(
            content=content,
            route=route,
            media=normalized_media,
            on_progress=on_progress,
            on_event=on_event,
            ephemeral=ephemeral,
            metadata=normalized_metadata,
        )

    def to_inbound_message(self, *, sender_id: str = "user") -> InboundMessage:
        msg = InboundMessage(
            channel=self.route.channel,
            sender_id=sender_id,
            chat_id=self.route.chat_id,
            content=self.content,
            media=list(self.media),
        )
        if self.metadata:
            msg.metadata.update(dict(self.metadata))
        if self.ephemeral:
            msg.metadata["_ephemeral"] = True
        return msg
