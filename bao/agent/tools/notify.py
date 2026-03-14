"""Notify tool for explicit external delivery."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from bao.agent.reply_route import TurnContextStore
from bao.agent.tools.base import Tool
from bao.bus.events import OutboundMessage


class NotifyTool(Tool):
    """Tool to send an explicit notification to another channel/chat."""

    def __init__(self, send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None):
        self._send_callback = send_callback
        self._route = TurnContextStore("notify_route")

    def set_context(
        self,
        channel: str,
        chat_id: str,
        *,
        session_key: str | None = None,
        lang: str = "en",
        message_id: str | int | None = None,
        reply_metadata: dict[str, Any] | None = None,
    ) -> None:
        self._route.set(
            channel=channel,
            chat_id=chat_id,
            session_key=session_key,
            lang=lang,
            message_id=message_id,
            reply_metadata=reply_metadata,
        )

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        self._send_callback = callback

    @property
    def name(self) -> str:
        return "notify"

    @property
    def description(self) -> str:
        return "Send an explicit notification to another channel or chat. Do not use for the current session reply."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Optional text to send with the notification",
                },
                "channel": {"type": "string", "description": "Target channel"},
                "chat_id": {"type": "string", "description": "Target chat or user ID"},
                "reply_to": {
                    "type": "string",
                    "description": "Optional target message ID for the external delivery",
                },
                "media": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of local file paths to attach",
                },
            },
            "required": ["channel", "chat_id"],
        }

    async def execute(self, **kwargs: Any) -> str:
        content = kwargs.get("content", "")
        channel = kwargs.get("channel", "")
        chat_id = kwargs.get("chat_id", "")
        reply_to = kwargs.get("reply_to")
        media = kwargs.get("media")

        if not isinstance(content, str):
            return "Error: content must be a string"
        if not isinstance(channel, str):
            return "Error: channel must be a string"
        if not isinstance(chat_id, str):
            return "Error: chat_id must be a string"
        if reply_to is not None and not isinstance(reply_to, str):
            return "Error: reply_to must be a string"
        if media is not None and not isinstance(media, list):
            return "Error: media must be a list of file paths"

        normalized_channel = channel.strip().lower()
        normalized_chat_id = chat_id.strip()
        if not normalized_channel or not normalized_chat_id:
            return "Error: notify requires explicit channel and chat_id."
        if normalized_channel == "desktop":
            return "Error: notify cannot send to desktop. Reply through the normal desktop path."
        if not self._send_callback:
            return "Error: notification sending not configured"

        route = self._route.get()
        if normalized_channel == route.channel and normalized_chat_id == route.chat_id:
            return "Error: notify is only for explicit external delivery. Use the normal reply path for the current session."
        media_list = [item for item in media or [] if isinstance(item, str) and item.strip()]
        if not content.strip() and not media_list:
            return "Error: notify requires content or media."

        try:
            await self._send_callback(
                OutboundMessage(
                    channel=normalized_channel,
                    chat_id=normalized_chat_id,
                    content=content,
                    reply_to=reply_to.strip() if isinstance(reply_to, str) and reply_to.strip() else None,
                    media=media_list,
                    metadata={},
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return f"Error sending notification: {exc}"

        media_info = f" +{len(media_list)} files" if media_list else ""
        preview = content[:60].replace("\n", " ").replace("\r", "")
        if len(content) > 60:
            preview += "..."
        if not preview:
            preview = "[media only]"
        return f"Notification sent to {normalized_channel}:{normalized_chat_id}{media_info}: {preview}"
