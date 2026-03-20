"""Slack inbound socket helpers."""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from slack_sdk.socket_mode.async_client import AsyncBaseSocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from bao.bus.events import InboundMessage


@dataclass(frozen=True)
class _SlackThreadContext:
    channel_type: str
    chat_id: str
    thread_ts: str | None


class _SlackInboundMixin:
    @staticmethod
    def _event_payload(req: SocketModeRequest) -> tuple[dict[str, object], dict[str, object]]:
        payload = req.payload or {}
        event = payload.get("event") or {}
        return payload, event

    @staticmethod
    def _slack_metadata(
        event: dict[str, object],
        context: _SlackThreadContext,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {
            "slack": {
                "event": event,
                "thread_ts": context.thread_ts,
                "channel_type": context.channel_type,
            }
        }
        if context.channel_type != "im" and context.thread_ts:
            metadata["session_key"] = f"slack:{context.chat_id}:{context.thread_ts}"
        return metadata

    async def _on_socket_request(
        self,
        client: AsyncBaseSocketModeClient,
        req: SocketModeRequest,
    ) -> None:
        if req.type != "events_api":
            return

        await client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

        _, event = self._event_payload(req)
        event_type = event.get("type")
        if event_type not in ("message", "app_mention"):
            return

        sender_id = event.get("user")
        chat_id = event.get("channel")
        if event.get("subtype"):
            return
        if self._bot_user_id and sender_id == self._bot_user_id:
            return

        text = event.get("text") or ""
        if event_type == "message" and self._bot_user_id and f"<@{self._bot_user_id}>" in text:
            return

        logger.debug(
            "Slack event: type={} subtype={} user={} channel={} channel_type={} text={}",
            event_type,
            event.get("subtype"),
            sender_id,
            chat_id,
            event.get("channel_type"),
            text[:80],
        )
        if not sender_id or not chat_id:
            return

        channel_type = event.get("channel_type") or ""
        if not self._is_allowed(sender_id, chat_id, channel_type):
            return
        if channel_type != "im" and not self._should_respond_in_channel(event_type, text, chat_id):
            return

        text = self._strip_bot_mention(text)
        thread_ts = event.get("thread_ts") or (event.get("ts") if self.config.reply_in_thread else None)
        context = _SlackThreadContext(channel_type=channel_type, chat_id=chat_id, thread_ts=thread_ts)
        await self._add_reaction(chat_id, event.get("ts"))

        try:
            await self._handle_message(
                InboundMessage(
                    channel=self.name,
                    sender_id=sender_id,
                    chat_id=chat_id,
                    content=text,
                    metadata=self._slack_metadata(event, context),
                )
            )
        except Exception:
            logger.exception("❌ 处理失败 / message error: {}", sender_id)

    async def _add_reaction(self, chat_id: str, event_ts: str | None) -> None:
        try:
            if self._web_client and isinstance(event_ts, str) and event_ts:
                await self._web_client.reactions_add(
                    channel=chat_id,
                    name=self.config.react_emoji,
                    timestamp=event_ts,
                )
        except Exception as exc:
            logger.debug("Slack reactions_add failed: {}", exc)
