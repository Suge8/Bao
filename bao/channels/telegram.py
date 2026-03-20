"""Telegram channel implementation using python-telegram-bot."""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger
from telegram import BotCommand, ReplyParameters
from telegram.error import TelegramError
from telegram.ext import Application
from telegram.request import HTTPXRequest

from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.channels.progress_text import EditingProgress, EditingProgressOps
from bao.command_text import iter_telegram_command_specs
from bao.config.paths import get_media_dir
from bao.config.schema import TelegramConfig

from . import _telegram_common as _telegram_common
from ._telegram_inbound import _TelegramInboundMixin
from ._telegram_lifecycle import _TelegramLifecycleMixin
from ._telegram_metadata import _TelegramMetadataMixin
from ._telegram_outbound import _TelegramOutboundMixin

_UPDATER_CLEANUP_LOG = _telegram_common._UPDATER_CLEANUP_LOG
_split_message = _telegram_common._split_message


def _on_polling_error(exc: TelegramError) -> None:
    _telegram_common._on_polling_error(exc, logger)


__all__ = [
    "Application",
    "HTTPXRequest",
    "TelegramChannel",
    "_UPDATER_CLEANUP_LOG",
    "_on_polling_error",
    "_split_message",
    "get_media_dir",
    "logger",
]


class TelegramChannel(
    _TelegramLifecycleMixin,
    _TelegramOutboundMixin,
    _TelegramMetadataMixin,
    _TelegramInboundMixin,
    BaseChannel,
):
    """Telegram channel using long polling."""

    name = "telegram"

    BOT_COMMANDS = tuple(BotCommand(spec.name, spec.description) for spec in iter_telegram_command_specs())

    def __init__(
        self,
        config: TelegramConfig,
        bus: MessageBus,
        groq_api_key: str = "",
    ):
        super().__init__(config, bus)
        self.config: TelegramConfig = config
        self.groq_api_key = groq_api_key
        self._app: Any = None
        self._chat_ids: dict[str, int] = {}  # Map sender_id to chat_id for replies
        self._typing_tasks: dict[str, asyncio.Task[None]] = {}  # chat_id -> typing loop task
        self._media_group_buffers: dict[str, list[dict[str, object]]] = {}
        self._media_group_tasks: dict[str, asyncio.Task[None]] = {}
        self._progress_reply_params: dict[str, ReplyParameters | None] = {}
        self._progress_thread_kwargs: dict[str, dict[str, int]] = {}
        self._message_threads: dict[tuple[str, int], int] = {}
        self._bot_user_id: int | None = None
        self._bot_username: str | None = None
        self._progress_handler = EditingProgress(
            EditingProgressOps(
                create=self._create_progress_text,
                update=self._update_progress_text,
                split=_split_message,
            ),
            rewrite_final=False,
        )
