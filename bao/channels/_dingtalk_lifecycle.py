"""DingTalk lifecycle helpers."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import httpx
from loguru import logger


class _DingTalkLifecycleMixin:
    def _build_stream_handler(
        self,
        callback_handler_cls: type,
        chatbot_message_cls: type,
        ack_message_cls: type,
    ):
        if TYPE_CHECKING:

            class _Handler(object):
                def __init__(self, channel):
                    self.channel = channel

                async def process(self, message: Any) -> Any:
                    _ = message
                    raise NotImplementedError

        else:

            class _Handler(callback_handler_cls):
                def __init__(self, channel):
                    super().__init__()
                    self.channel = channel

                async def process(self, message: Any) -> Any:
                    try:
                        raw = getattr(message, "data", None) or {}
                        chatbot_msg = chatbot_message_cls.from_dict(raw)
                        content = self.channel._extract_message_content(chatbot_msg, raw)
                        if not content:
                            return ack_message_cls.STATUS_OK, "OK"
                        sender_id = str(
                            getattr(chatbot_msg, "sender_staff_id", None)
                            or getattr(chatbot_msg, "sender_id", None)
                            or ""
                        )
                        sender_name = getattr(chatbot_msg, "sender_nick", None) or "Unknown"
                        conversation_type, conversation_id = self.channel._extract_conversation(raw)
                        from ._dingtalk_inbound import _DingTalkInboundPayload

                        task = asyncio.create_task(
                            self.channel._on_message(
                                _DingTalkInboundPayload(
                                    content=content,
                                    sender_id=sender_id,
                                    sender_name=sender_name,
                                    conversation_type=conversation_type,
                                    conversation_id=conversation_id,
                                )
                            )
                        )
                        self.channel._background_tasks.add(task)
                        task.add_done_callback(self.channel._background_tasks.discard)
                        return ack_message_cls.STATUS_OK, "OK"
                    except Exception as exc:
                        logger.error("❌ 钉钉消息处理异常 / process error: {}", exc)
                        return ack_message_cls.STATUS_OK, "Error"

        return _Handler(self)

    async def start(self) -> None:
        from . import dingtalk as dingtalk_module

        self.mark_not_ready()
        try:
            if not dingtalk_module.DINGTALK_AVAILABLE:
                logger.error("❌ 钉钉 SDK 未安装 / sdk missing: pip install dingtalk-stream")
                self.mark_ready()
                return

            from dingtalk_stream import (
                AckMessage,
                CallbackHandler,
                Credential,
                DingTalkStreamClient,
            )
            from dingtalk_stream.chatbot import ChatbotMessage

            client_secret = self.config.client_secret.get_secret_value()
            if not self.config.client_id or not client_secret:
                logger.error("❌ 钉钉配置缺失 / config missing: client_id and client_secret")
                self.mark_ready()
                return

            self._start_lifecycle()
            self._http = httpx.AsyncClient()
            self.mark_ready()

            logger.info("📡 钉钉开始连接 / stream init: client_id={}...", self.config.client_id)
            credential = Credential(self.config.client_id, client_secret)
            self._client = DingTalkStreamClient(credential)
            handler = self._build_stream_handler(
                CallbackHandler,
                ChatbotMessage,
                AckMessage,
            )
            self._client.register_callback_handler(ChatbotMessage.TOPIC, handler)

            logger.info("✅ 钉钉已连接 / stream connected: stream mode started")
            await self._run_reconnect_loop(self._client.start, label="钉钉 Stream")
        except Exception as exc:
            logger.exception("❌ 钉钉启动失败 / start failed: {}", exc)
            self.mark_ready()

    async def stop(self) -> None:
        self._clear_progress()
        self._stop_lifecycle()
        self.mark_not_ready()
        if self._http:
            await self._http.aclose()
            self._http = None
        for task in self._background_tasks:
            task.cancel()
        self._background_tasks.clear()
        self._reset_lifecycle()
