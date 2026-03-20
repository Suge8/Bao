from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from bao.agent.protocol import StreamEvent


@dataclass(frozen=True, slots=True)
class HubSendRequest:
    content: str
    session_key: str
    channel: str = "hub"
    chat_id: str = "direct"
    profile_id: str = ""
    reply_target_id: str | int | None = None
    media: list[str] | None = None
    on_progress: Callable[[str], Awaitable[None]] | None = None
    on_event: Callable[[StreamEvent], Awaitable[None]] | None = None
    ephemeral: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HubStopRequest:
    session_key: str
    profile_id: str = ""


@dataclass(frozen=True, slots=True)
class HubDeleteRequest:
    session_key: str
    profile_id: str = ""
    include_children: bool = True


@dataclass(frozen=True, slots=True)
class HubSpawnChildRequest:
    task: str
    session_key: str
    label: str | None = None
    profile_id: str = ""
    origin_channel: str = "hub"
    origin_chat_id: str = "direct"
    context_from: str | None = None
    child_session_key: str | None = None


@dataclass(frozen=True, slots=True)
class HubCreateSessionRequest:
    session_key: str
    natural_key: str
    profile_id: str = ""
    activate: bool = True


@dataclass(frozen=True, slots=True)
class HubSetActiveSessionRequest:
    natural_key: str
    session_key: str
    profile_id: str = ""


@dataclass(frozen=True, slots=True)
class HubClearActiveSessionRequest:
    natural_key: str
    profile_id: str = ""
