"""Slack channel implementation using Socket Mode."""

from __future__ import annotations

from slack_sdk.socket_mode.websockets import SocketModeClient
from slack_sdk.web.async_client import AsyncWebClient

from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.channels.progress_text import EditingProgress, EditingProgressOps
from bao.config.schema import SlackConfig

from ._slack_format import _SlackFormatMixin
from ._slack_inbound import _SlackInboundMixin
from ._slack_lifecycle import _SlackLifecycleMixin
from ._slack_outbound import _SlackOutboundMixin

__all__ = ["AsyncWebClient", "SlackChannel", "SocketModeClient"]


class SlackChannel(
    _SlackLifecycleMixin,
    _SlackOutboundMixin,
    _SlackInboundMixin,
    _SlackFormatMixin,
    BaseChannel,
):
    """Slack channel using Socket Mode."""

    name = "slack"

    def __init__(self, config: SlackConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: SlackConfig = config
        self._web_client: AsyncWebClient | None = None
        self._socket_client: SocketModeClient | None = None
        self._bot_user_id: str | None = None
        self._progress_threads: dict[str, str | None] = {}
        self._progress_handler = EditingProgress(
            EditingProgressOps(
                create=self._create_progress_text,
                update=self._update_progress_text,
            )
        )
