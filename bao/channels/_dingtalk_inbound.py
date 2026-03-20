"""DingTalk inbound helpers."""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from bao.bus.events import InboundMessage


@dataclass(frozen=True)
class _DingTalkInboundPayload:
    content: str
    sender_id: str
    sender_name: str
    conversation_type: str | None = None
    conversation_id: str | None = None


class _DingTalkInboundMixin:
    async def _on_message(self, payload: _DingTalkInboundPayload) -> None:
        try:
            logger.debug("ℹ️ 钉钉入站消息 / inbound: {} from {}", payload.content, payload.sender_name)
            await self._handle_message(
                InboundMessage(
                    channel=self.name,
                    sender_id=payload.sender_id,
                    chat_id=self._build_chat_id(
                        payload.sender_id,
                        payload.conversation_type,
                        payload.conversation_id,
                    ),
                    content=str(payload.content),
                    metadata=self._build_metadata(
                        payload.sender_name,
                        payload.conversation_type,
                        payload.conversation_id,
                    ),
                )
            )
        except Exception as exc:
            logger.error("❌ 钉钉消息转发异常 / publish error: {}", exc)
