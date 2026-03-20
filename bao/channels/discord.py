"""Discord channel implementation using Discord Gateway websocket."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import websockets

from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.channels.progress_text import EditingProgress, EditingProgressOps
from bao.config.paths import get_media_dir
from bao.config.schema import DiscordConfig

from . import _discord_common as _discord_common
from ._discord_inbound import _DiscordInboundMixin
from ._discord_lifecycle import _DiscordLifecycleMixin
from ._discord_outbound import _DiscordOutboundMixin

DISCORD_API_BASE = _discord_common.DISCORD_API_BASE
MAX_ATTACHMENT_BYTES = _discord_common.MAX_ATTACHMENT_BYTES
MAX_MESSAGE_LEN = _discord_common.MAX_MESSAGE_LEN
_split_message = _discord_common._split_message

__all__ = ["DiscordChannel", "websockets", "get_media_dir"]


class DiscordChannel(
    _DiscordLifecycleMixin,
    _DiscordOutboundMixin,
    _DiscordInboundMixin,
    BaseChannel,
):
    """Discord channel using Gateway websocket."""

    name = "discord"

    def __init__(self, config: DiscordConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: DiscordConfig = config
        self._ws: Any = None
        self._seq: int | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._typing_tasks: dict[str, asyncio.Task[None]] = {}
        self._http: httpx.AsyncClient | None = None
        self._progress_reply_to: dict[str, str | None] = {}
        self._bot_user_id: str | None = None
        self._progress_handler = EditingProgress(
            EditingProgressOps(
                create=self._create_progress_text,
                update=self._update_progress_text,
                split=_split_message,
            )
        )
        # RESUME support
        self._session_id: str | None = None
        self._resume_gateway_url: str | None = None
        self._heartbeat_acked: bool = True
        self._should_resume: bool = False
