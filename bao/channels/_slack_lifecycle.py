"""Slack lifecycle helpers."""

from __future__ import annotations

from loguru import logger


class _SlackLifecycleMixin:
    async def start(self) -> None:
        from . import slack as slack_module

        bot_token = self.config.bot_token.get_secret_value()
        app_token = self.config.app_token.get_secret_value()
        if not bot_token or not app_token:
            logger.error("❌ 未配置 / not configured: Slack token")
            return
        if self.config.mode != "socket":
            logger.error("❌ 模式错误 / unsupported mode: {}", self.config.mode)
            return

        self._start_lifecycle()
        self._web_client = slack_module.AsyncWebClient(token=bot_token)
        self._socket_client = slack_module.SocketModeClient(
            app_token=app_token,
            web_client=self._web_client,
        )
        self._socket_client.socket_mode_request_listeners.append(self._on_socket_request)

        try:
            auth = await self._web_client.auth_test()
            self._bot_user_id = auth.get("user_id")
            logger.info("✅ 连接成功 / connected as: {}", self._bot_user_id)
        except Exception as exc:
            logger.warning("⚠️ 认证失败 / auth failed: {}", exc)

        logger.info("📡 启动通道 / starting: Slack socket mode")
        await self._socket_client.connect()
        await self._wait_until_stopped()

    async def stop(self) -> None:
        self._clear_progress()
        self._progress_threads.clear()
        self._stop_lifecycle()
        if self._socket_client:
            try:
                await self._socket_client.close()
            except Exception as exc:
                logger.debug("Slack socket close failed: {}", exc)
            self._socket_client = None
        self._reset_lifecycle()
