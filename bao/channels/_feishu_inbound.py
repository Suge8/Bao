"""Feishu inbound event helpers."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from loguru import logger

from bao.bus.events import InboundMessage

from ._feishu_extract import MSG_TYPE_MAP, _extract_post_text, _extract_share_card_content


class _FeishuInboundMixin:
    async def _build_message_payload(
        self,
        message: Any,
        msg_type: str,
        message_id: str,
    ) -> tuple[str, list[str]]:
        try:
            content_json = json.loads(message.content) if message.content else {}
        except json.JSONDecodeError:
            content_json = {}

        content_parts: list[str] = []
        media_paths: list[str] = []
        if msg_type == "text":
            text = content_json.get("text", "")
            if text:
                content_parts.append(text)
        elif msg_type == "post":
            text = _extract_post_text(content_json)
            if text:
                content_parts.append(text)
        elif msg_type in ("image", "audio", "file", "media"):
            file_path, content_text = await self._download_and_save_media(
                msg_type,
                content_json,
                message_id,
            )
            if file_path:
                media_paths.append(file_path)
            content_parts.append(content_text)
        elif msg_type in (
            "share_chat",
            "share_user",
            "interactive",
            "share_calendar_event",
            "system",
            "merge_forward",
        ):
            text = _extract_share_card_content(content_json, msg_type)
            if text:
                content_parts.append(text)
        else:
            content_parts.append(MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]"))
        return "\n".join(content_parts) if content_parts else "", media_paths

    def _on_message_sync(self, data: Any) -> None:
        if self._running and self._loop and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._on_message(data), self._loop)
            except RuntimeError:
                logger.debug("Feishu: event loop closed, dropping message")

    async def _on_message(self, data: Any) -> None:
        try:
            if not self._running:
                return

            event = data.event
            message = event.message
            sender = event.sender

            message_id = str(message.message_id or "")
            if not message_id or message_id in self._processed_message_ids:
                return
            self._processed_message_ids[message_id] = None

            while len(self._processed_message_ids) > 1000:
                self._processed_message_ids.popitem(last=False)

            if sender.sender_type == "bot":
                return

            sender_id = str(sender.sender_id.open_id) if sender.sender_id else "unknown"
            chat_id = str(message.chat_id or "")
            chat_type = str(message.chat_type or "")
            msg_type = str(message.message_type or "")

            if chat_type == "group" and not self._is_group_message_for_bot(message):
                logger.debug("Feishu: skipping group message (not mentioned)")
                return

            await self._add_reaction(message_id, self.config.react_emoji)

            content, media_paths = await self._build_message_payload(message, msg_type, message_id)
            if not content and not media_paths:
                return
            if not self._running:
                return

            reply_to = chat_id if chat_type == "group" else sender_id
            await self._handle_message(
                InboundMessage(
                    channel=self.name,
                    sender_id=sender_id,
                    chat_id=reply_to,
                    content=content,
                    media=media_paths,
                    metadata={
                        "message_id": message_id,
                        "chat_type": chat_type,
                        "msg_type": msg_type,
                    },
                )
            )
        except Exception as exc:
            logger.error("❌ 飞书消息处理异常 / process error: {}", exc)
