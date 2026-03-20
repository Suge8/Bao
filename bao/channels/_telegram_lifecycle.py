"""Telegram channel lifecycle mixin."""

from __future__ import annotations

import asyncio

from loguru import logger
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters

from bao.command_text import iter_telegram_forward_command_names

from ._telegram_common import (
    _run_start_step,
    _suppress_updater_cleanup_log,
)


class _TelegramLifecycleMixin:
    def _build_application(self, token: str):
        from . import telegram as telegram_module

        api_req = telegram_module.HTTPXRequest(
            connection_pool_size=16,
            pool_timeout=5.0,
            connect_timeout=30.0,
            read_timeout=30.0,
            proxy=self.config.proxy or None,
        )
        poll_req = telegram_module.HTTPXRequest(
            connection_pool_size=1,
            pool_timeout=5.0,
            connect_timeout=30.0,
            read_timeout=30.0,
            proxy=self.config.proxy or None,
        )
        builder = (
            telegram_module.Application.builder()
            .token(token)
            .request(api_req)
            .get_updates_request(poll_req)
        )
        return builder.build()

    def _register_handlers(self, app) -> None:
        app.add_error_handler(self._on_error)
        app.add_handler(CommandHandler("start", self._on_start))
        for command_name in iter_telegram_forward_command_names():
            app.add_handler(CommandHandler(command_name, self._forward_command))
        app.add_handler(
            MessageHandler(
                (
                    filters.TEXT
                    | filters.PHOTO
                    | filters.VOICE
                    | filters.AUDIO
                    | filters.Document.ALL
                )
                & ~filters.COMMAND,
                self._on_message,
            )
        )

    async def start(self) -> None:
        from . import telegram as telegram_module

        self.mark_not_ready()
        token = self.config.token.get_secret_value()
        if not token:
            logger.error("❌ 未配置 / not configured: Telegram token")
            self.mark_ready()
            return

        self._start_lifecycle()
        self._app = self._build_application(token)
        app = self._app
        self._register_handlers(app)

        logger.info("📡 启动通道 / starting: Telegram polling")

        await _run_start_step("bot_initialize", app.bot.initialize)
        await _run_start_step("application_initialize", app.initialize)
        await _run_start_step("start", app.start)

        bot_info = await _run_start_step("get_me", app.bot.get_me)
        self._bot_user_id = getattr(bot_info, "id", None)
        self._bot_username = getattr(bot_info, "username", None)
        logger.info("✅ 连接成功 / connected: @{}", bot_info.username)
        self.mark_ready()

        try:
            await app.bot.set_my_commands(self.BOT_COMMANDS)
            logger.debug("Telegram bot commands registered")
        except Exception as exc:
            logger.warning("⚠️ 注册失败 / register failed: {}", exc)

        updater = app.updater
        assert updater is not None
        await _run_start_step(
            "start_polling",
            lambda: updater.start_polling(
                allowed_updates=["message"],
                drop_pending_updates=True,
                error_callback=telegram_module._on_polling_error,
            ),
        )

        await self._wait_until_stopped()

    async def stop(self) -> None:
        self._stop_lifecycle()
        self.mark_not_ready()
        self._clear_progress()
        self._progress_reply_params.clear()
        self._progress_thread_kwargs.clear()

        for chat_id in list(self._typing_tasks):
            self._stop_typing(chat_id)

        flush_tasks = list(self._media_group_tasks.values())
        for task in flush_tasks:
            if not task.done():
                task.cancel()
        if flush_tasks:
            await asyncio.gather(*flush_tasks, return_exceptions=True)
        self._media_group_tasks.clear()
        self._media_group_buffers.clear()

        if self._app:
            app = self._app
            logger.info("📡 停止通道 / stopping: Telegram bot")
            updater = getattr(app, "updater", None)
            if updater is not None and getattr(updater, "running", False):
                with _suppress_updater_cleanup_log():
                    await updater.stop()
            await app.stop()
            await app.shutdown()
            self._app = None
        self._reset_lifecycle()

    async def _on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        del update
        logger.error("❌ 处理异常 / handler error: {}", context.error)
