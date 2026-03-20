from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from bao.agent.dispatch_models import RouteKey, WakeRequest
from bao.agent.protocol import StreamEvent
from bao.bus.events import InboundMessage
from bao.session.manager import Session


@dataclass(slots=True)
class ProcessMessageOptions:
    session_key: str | None = None
    on_progress: Callable[[str], Awaitable[None]] | None = None
    on_event: Callable[[StreamEvent], Awaitable[None]] | None = None
    expected_generation: int | None = None
    expected_generation_key: str | None = None


@dataclass(slots=True)
class UserTurnRequest:
    msg: InboundMessage
    session: Session
    session_lang: str
    initial_messages: list[dict[str, Any]]
    on_progress: Callable[[str], Awaitable[None]] | None = None
    on_event: Callable[[StreamEvent], Awaitable[None]] | None = None


@dataclass(slots=True)
class FinalizeUserTurnRequest:
    msg: InboundMessage
    session: Session
    session_key: str
    recall: dict[str, Any]
    parsed_result: Any
    final_content: str
    expected_generation: int | None = None
    expected_generation_key: str | None = None


@dataclass(slots=True)
class ProcessedMessageContext:
    msg: InboundMessage
    session: Session
    session_key: str
    natural_key: str
    track_running: bool


@dataclass(slots=True)
class ProcessDirectRequest:
    content: str
    session_key: str = "hub:direct"
    channel: str = "hub"
    chat_id: str = "direct"
    profile_id: str | None = None
    reply_target_id: str | int | None = None
    media: list[str] | None = None
    on_progress: Callable[[str], Awaitable[None]] | None = None
    on_event: Callable[[StreamEvent], Awaitable[None]] | None = None
    ephemeral: bool = False
    metadata: dict[str, Any] | None = None

    def _route_session_key(self) -> str | None:
        session_key = str(self.session_key or "").strip()
        if session_key != "hub:direct":
            return session_key or None
        channel = str(self.channel or "").strip().lower()
        chat_id = str(self.chat_id or "").strip()
        if channel == "hub" and chat_id == "direct":
            return session_key
        return None

    def to_route_key(self) -> RouteKey:
        return RouteKey.create(
            profile_id=self.profile_id or "",
            session_key=self._route_session_key(),
            channel=self.channel,
            chat_id=self.chat_id,
            reply_target_id=self.reply_target_id,
        )

    def to_wake_request(self) -> WakeRequest:
        return WakeRequest.create(
            content=self.content,
            route=self.to_route_key(),
            media=self.media,
            on_progress=self.on_progress,
            on_event=self.on_event,
            ephemeral=self.ephemeral,
            metadata=self.metadata,
        )
