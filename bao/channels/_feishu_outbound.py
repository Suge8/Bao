"""Feishu outbound message helpers."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass

from loguru import logger

from bao.bus.events import OutboundMessage


@dataclass(frozen=True)
class _FeishuSendRequest:
    receive_id_type: str
    receive_id: str
    msg_type: str
    content: str


class _FeishuOutboundMixin:
    def _send_message_sync(self, request_data: _FeishuSendRequest) -> str | None:
        from . import feishu as feishu_module

        try:
            request = (
                feishu_module.CreateMessageRequest.builder()
                .receive_id_type(request_data.receive_id_type)
                .request_body(
                    feishu_module.CreateMessageRequestBody.builder()
                    .receive_id(request_data.receive_id)
                    .msg_type(request_data.msg_type)
                    .content(request_data.content)
                    .build()
                )
                .build()
            )
            response = self._client.im.v1.message.create(request)
            if not response.success():
                logger.error(
                    "❌ 飞书消息发送失败 / send failed: {} code={}, msg={}, log_id={}",
                    request_data.msg_type,
                    response.code,
                    response.msg,
                    response.get_log_id(),
                )
                return None
            logger.debug("Feishu {} message sent to {}", request_data.msg_type, request_data.receive_id)
            data = getattr(response, "data", None)
            message_id = getattr(data, "message_id", None)
            return str(message_id) if message_id else None
        except Exception as exc:
            logger.error("❌ 飞书消息发送异常 / send error: {}: {}", request_data.msg_type, exc)
            return None

    @staticmethod
    def _build_card_payload(elements: list[dict[str, object]]) -> str:
        return json.dumps(
            {"config": {"wide_screen_mode": True}, "elements": elements},
            ensure_ascii=False,
        )

    @staticmethod
    def _get_receive_id_type(chat_id: str) -> str:
        return "chat_id" if chat_id.startswith("oc_") else "open_id"

    async def _send_message_content(
        self,
        chat_id: str,
        msg_type: str,
        content: str,
    ) -> str | None:
        if not self._client:
            return None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._send_message_sync,
            _FeishuSendRequest(
                receive_id_type=self._get_receive_id_type(chat_id),
                receive_id=chat_id,
                msg_type=msg_type,
                content=content,
            ),
        )

    async def _send_interactive_elements(
        self,
        chat_id: str,
        elements: list[dict[str, object]],
    ) -> str | None:
        return await self._send_message_content(
            chat_id,
            "interactive",
            self._build_card_payload(elements),
        )

    async def _send_json_message(
        self,
        chat_id: str,
        msg_type: str,
        payload: dict[str, object],
    ) -> str | None:
        return await self._send_message_content(
            chat_id,
            msg_type,
            json.dumps(payload, ensure_ascii=False),
        )

    async def _send_text_content(self, chat_id: str, content: str) -> str | None:
        if not self._client or not content.strip():
            return None

        msg_format = self._detect_msg_format(content)
        if msg_format == "text":
            return await self._send_json_message(chat_id, "text", {"text": content})
        if msg_format == "post":
            return await self._send_json_message(chat_id, "post", self._markdown_to_post(content))

        handle = None
        elements = self._build_card_elements(content)
        for chunk in self._split_elements_by_table_limit(elements):
            handle = await self._send_interactive_elements(chat_id, chunk)
        return handle

    def _has_active_progress(self, chat_id: str) -> bool:
        handler = self._progress_handler
        return bool(
            getattr(handler, "_buf", {}).get(chat_id)
            or getattr(handler, "_open", {}).get(chat_id)
            or getattr(handler, "_handles", {}).get(chat_id)
        )

    def _patch_message_sync(self, message_id: str, content: str) -> bool:
        from . import feishu as feishu_module

        if (
            not self._client
            or not feishu_module.PatchMessageRequest
            or not feishu_module.PatchMessageRequestBody
        ):
            return False
        try:
            request = (
                feishu_module.PatchMessageRequest.builder()
                .message_id(message_id)
                .request_body(feishu_module.PatchMessageRequestBody.builder().content(content).build())
                .build()
            )
            response = self._client.im.v1.message.patch(request)
            if not response.success():
                logger.error(
                    "❌ 飞书消息更新失败 / patch failed: code={}, msg={}, log_id={}",
                    response.code,
                    response.msg,
                    response.get_log_id(),
                )
                return False
            return True
        except Exception as exc:
            logger.error("❌ 飞书消息更新异常 / patch error: {}", exc)
            return False

    async def send(self, msg: OutboundMessage) -> None:
        if not self._client:
            logger.warning("⚠️ 飞书客户端未就绪 / client not ready: not initialized")
            return

        try:
            loop = asyncio.get_running_loop()

            for file_path in msg.media:
                if not os.path.isfile(file_path):
                    logger.warning("⚠️ 飞书媒体缺失 / media missing: {}", file_path)
                    continue
                ext = os.path.splitext(file_path)[1].lower()
                if ext in self._IMAGE_EXTS:
                    key = await loop.run_in_executor(None, self._upload_image_sync, file_path)
                    if key:
                        await self._send_json_message(msg.chat_id, "image", {"image_key": key})
                else:
                    key = await loop.run_in_executor(None, self._upload_file_sync, file_path)
                    if key:
                        media_type = (
                            "media" if ext in self._AUDIO_EXTS or ext in self._VIDEO_EXTS else "file"
                        )
                        await self._send_json_message(msg.chat_id, media_type, {"file_key": key})

            meta = msg.metadata or {}
            if (
                msg.content
                and not meta.get("_progress")
                and not meta.get("_progress_clear")
                and not self._has_active_progress(msg.chat_id)
            ):
                await self._send_text_content(msg.chat_id, msg.content)
            elif msg.content or meta.get("_progress_clear"):
                await self._dispatch_progress_text(msg, flush_progress=True)
        except Exception as exc:
            logger.error("❌ 飞书发送异常 / send error: {}", exc)

    async def _send_text(self, chat_id: str, text: str) -> None:
        if not self._client or not text.strip():
            return
        await self._send_interactive_elements(chat_id, self._build_card_elements(text))

    async def _create_progress_text(self, chat_id: str, text: str) -> str | None:
        if not self._client or not text.strip():
            return None
        return await self._send_interactive_elements(chat_id, self._build_card_elements(text))

    async def _update_progress_text(
        self,
        chat_id: str,
        handle: str | None,
        text: str,
    ) -> str | None:
        del chat_id
        if not handle or not text.strip():
            return handle
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self._patch_message_sync,
            handle,
            self._build_card_payload(self._build_card_elements(text)),
        )
        return handle
