from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from bao.agent.protocol import StreamEvent
from bao.session.manager import Session


@dataclass(slots=True)
class ExecuteTurnLoopRequest:
    initial_messages: list[dict[str, Any]]
    session: Session
    session_lang: str
    fallback_text_fn: Callable[[str, bool], str]
    on_progress: Callable[[str], Awaitable[None]] | None = None
    on_tool_hint: Callable[[str], Awaitable[None]] | None = None
    on_event: Callable[[StreamEvent], Awaitable[None]] | None = None
    on_visible_assistant_turn: Callable[[str], Awaitable[None]] | None = None


@dataclass(slots=True)
class PersistAssistantTurnRequest:
    session: Session
    final_content: str
    tools_used: list[str]
    assistant_status: str
    reply_attachments: list[dict[str, Any]] | None = None
    references: dict[str, Any] | None = None


@dataclass(slots=True)
class ControlOutboundRequest:
    channel: str
    chat_id: str
    session_key: str
    final_content: str
    metadata: dict[str, Any] | None = None
    reply_attachments: list[dict[str, Any]] | None = None
