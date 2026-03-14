"""Message tool for sending messages to users."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from bao.agent.reply_route import TurnContextStore
from bao.agent.tools.base import Tool
from bao.bus.events import OutboundMessage


@dataclass
class _TurnState:
    sent_in_turn: bool = False
    last_sent_summary: str | None = None
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class MessageTool(Tool):
    """Tool to send messages to users on chat channels."""

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        default_channel: str = "",
        default_chat_id: str = "",
        default_message_id: str | None = None,
    ):
        self._send_callback = send_callback
        self._route = TurnContextStore(
            "message_route",
            channel=default_channel,
            chat_id=default_chat_id,
            message_id=default_message_id,
        )
        from contextvars import ContextVar

        self._turn_state_ctx: ContextVar[_TurnState | None] = ContextVar(
            "message_turn_state", default=None
        )

    def _turn_state(self) -> _TurnState:
        state = self._turn_state_ctx.get()
        if state is None:
            state = _TurnState()
            self._turn_state_ctx.set(state)
        return state

    @property
    def _sent_in_turn(self) -> bool:
        return self._turn_state().sent_in_turn

    @_sent_in_turn.setter
    def _sent_in_turn(self, value: bool) -> None:
        self._turn_state().sent_in_turn = bool(value)

    def set_context(
        self,
        channel: str,
        chat_id: str,
        message_id: str | None = None,
        reply_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Set the current message context."""
        self._route.set(
            channel=channel,
            chat_id=chat_id,
            message_id=message_id,
            reply_metadata=reply_metadata,
        )

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        """Set the callback for sending messages."""
        self._send_callback = callback

    def start_turn(self) -> None:
        """Reset per-turn send tracking."""
        self._turn_state_ctx.set(_TurnState())

    @property
    def last_sent_summary(self) -> str | None:
        return self._turn_state().last_sent_summary

    @property
    def name(self) -> str:
        return "message"

    @property
    def description(self) -> str:
        return "Send a message to the user."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The message content to send"},
                "channel": {
                    "type": "string",
                    "description": "Optional: target channel (telegram, discord, etc.)",
                },
                "chat_id": {"type": "string", "description": "Optional: target chat/user ID"},
                "reply_to": {
                    "type": "string",
                    "description": "Optional: target message ID to reply to",
                },
                "media": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: list of file paths to attach (images, audio, documents)",
                },
            },
            "required": ["content"],
        }

    async def execute(self, **kwargs: Any) -> str:
        content = kwargs.get("content", "")
        channel = kwargs.get("channel")
        chat_id = kwargs.get("chat_id")
        reply_to = kwargs.get("reply_to")
        message_id = kwargs.get("message_id")
        media = kwargs.get("media")

        if not isinstance(content, str):
            return "Error: content must be a string"

        if reply_to is not None and not isinstance(reply_to, str):
            return "Error: reply_to must be a string"

        if media is not None and not isinstance(media, list):
            return "Error: media must be a list of file paths"

        route = self._route.get()
        default_channel = route.channel
        default_chat_id = route.chat_id
        default_message_id = route.message_id
        reply_metadata = route.reply_metadata

        channel = channel or default_channel
        chat_id = chat_id or default_chat_id
        if isinstance(channel, str):
            channel = channel.strip().lower()
        if isinstance(chat_id, str):
            chat_id = chat_id.strip()
        message_id = message_id or default_message_id
        if not isinstance(message_id, str):
            message_id = None

        default_target = channel == default_channel and chat_id == default_chat_id
        effective_reply_to = reply_to or (message_id if default_target else None)
        outbound_metadata: dict[str, Any] = {"message_id": effective_reply_to}
        if default_target and isinstance(reply_metadata, dict):
            outbound_metadata.update(reply_metadata)

        if channel == "desktop":
            return "Error: message tool cannot send to desktop channel. Reply normally instead."

        if not content or not content.strip():
            return "Error: message content is empty. Provide non-empty content to send."

        if not channel or not chat_id:
            return "Error: No target channel/chat specified"

        if not self._send_callback:
            return "Error: Message sending not configured"

        turn_state = self._turn_state()
        async with turn_state.send_lock:
            if turn_state.sent_in_turn:
                return (
                    "Error: message tool already sent once in this turn. Do not call message again."
                )

            msg = OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content=content,
                reply_to=effective_reply_to,
                media=media or [],
                metadata=outbound_metadata,
            )

            try:
                await self._send_callback(msg)
                if channel == default_channel and chat_id == default_chat_id:
                    turn_state.sent_in_turn = True
                media_info = f" +{len(media)} files" if media else ""
                preview = content[:60].replace("\n", " ").replace("\r", "")
                if len(content) > 60:
                    preview += "..."
                turn_state.last_sent_summary = (
                    f"[message tool sent] {channel}:{chat_id}{media_info} {preview}"
                )
                return f"Message sent to {channel}:{chat_id}{media_info}: {preview}"
            except asyncio.CancelledError:
                raise
            except Exception as e:
                return f"Error sending message: {str(e)}"
