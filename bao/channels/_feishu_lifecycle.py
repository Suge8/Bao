"""Feishu channel lifecycle helpers."""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger


class _FeishuLifecycleMixin:
    async def start(self) -> None:
        from . import feishu as feishu_module

        self.mark_not_ready()
        if not feishu_module.FEISHU_AVAILABLE:
            logger.error("❌ 飞书SDK缺失 / sdk missing: pip install lark-oapi")
            self.mark_ready()
            return

        app_secret = self.config.app_secret.get_secret_value()
        encrypt_key = self.config.encrypt_key.get_secret_value()
        verification_token = self.config.verification_token.get_secret_value()

        if not self.config.app_id or not app_secret:
            logger.error("❌ 飞书配置缺失 / config missing: app_id and app_secret")
            self.mark_ready()
            return

        self._start_lifecycle()
        self._loop = asyncio.get_running_loop()
        self._client = (
            feishu_module.lark.Client.builder()
            .app_id(self.config.app_id)
            .app_secret(app_secret)
            .log_level(feishu_module.lark.LogLevel.INFO)
            .build()
        )
        self.mark_ready()

        event_handler = (
            feishu_module.lark.EventDispatcherHandler.builder(encrypt_key, verification_token)
            .register_p2_im_message_receive_v1(self._on_message_sync)
            .build()
        )
        self._ws_client = feishu_module.lark.ws.Client(
            self.config.app_id,
            app_secret,
            event_handler=event_handler,
            log_level=feishu_module.lark.LogLevel.INFO,
        )

        logger.info("✅ 飞书已连接 / ws connected: long connection started")
        logger.info("📡 飞书事件接收 / event recv: using WebSocket without public IP")
        await self._run_reconnect_loop(
            lambda: asyncio.to_thread(self._run_ws_client_blocking),
            label="飞书 WebSocket",
        )

    async def stop(self) -> None:
        self._stop_lifecycle()
        self.mark_not_ready()
        self._clear_progress()

        ws_client = self._ws_client
        if ws_client and hasattr(ws_client, "stop"):
            try:
                await asyncio.to_thread(ws_client.stop)
            except Exception as exc:
                logger.debug("Feishu ws stop failed: {}", exc)

        ws_thread = self._ws_thread
        if ws_thread and hasattr(ws_thread, "is_alive") and ws_thread.is_alive():
            try:
                await asyncio.to_thread(ws_thread.join, timeout=3)
            except Exception as exc:
                logger.debug("Feishu ws join failed: {}", exc)

        self._loop = None
        self._ws_thread = None
        self._ws_client = None
        self._reset_lifecycle()
        logger.info("ℹ️ 飞书已停止 / channel stopped: shutdown complete")

    def _run_ws_client_blocking(self) -> None:
        ws_client = self._ws_client
        if ws_client is None:
            return

        ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(ws_loop)
        try:
            try:
                import lark_oapi.ws.client as lark_ws_client

                setattr(lark_ws_client, "loop", ws_loop)
            except Exception:
                pass
            ws_client.start()
        finally:
            asyncio.set_event_loop(None)
            ws_loop.close()

    def _is_bot_mentioned(self, message: Any) -> bool:
        raw_content = getattr(message, "content", "") or ""
        if "@_all" in raw_content:
            return True

        for mention in getattr(message, "mentions", None) or []:
            mention_id = getattr(mention, "id", None)
            if not mention_id:
                continue
            if not getattr(mention_id, "user_id", None) and (
                getattr(mention_id, "open_id", None) or ""
            ).startswith("ou_"):
                return True
        return False

    def _is_group_message_for_bot(self, message: Any) -> bool:
        if self.config.group_policy == "open":
            return True
        return self._is_bot_mentioned(message)

    def _add_reaction_sync(self, message_id: str, emoji_type: str) -> None:
        from . import feishu as feishu_module

        try:
            request = (
                feishu_module.CreateMessageReactionRequest.builder()
                .message_id(message_id)
                .request_body(
                    feishu_module.CreateMessageReactionRequestBody.builder()
                    .reaction_type(feishu_module.Emoji.builder().emoji_type(emoji_type).build())
                    .build()
                )
                .build()
            )
            response = self._client.im.v1.message_reaction.create(request)

            if not response.success():
                logger.debug(
                    "ℹ️ 飞书表情失败 / react failed: code={}, msg={}",
                    response.code,
                    response.msg,
                )
            else:
                logger.debug("Added {} reaction to message {}", emoji_type, message_id)
        except Exception as exc:
            logger.debug("ℹ️ 飞书表情异常 / react error: {}", exc)

    async def _add_reaction(self, message_id: str, emoji_type: str = "THUMBSUP") -> None:
        from . import feishu as feishu_module

        if not self._client or not feishu_module.Emoji:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._add_reaction_sync, message_id, emoji_type)
