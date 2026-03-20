"""Mochat channel implementation using Socket.IO with HTTP polling fallback."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

import httpx

from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.config.schema import MochatConfig
from bao.utils.helpers import get_data_path

from ._mochat_common import (
    DelayState,
    _str_field,
)
from ._mochat_cursor import _MochatCursorMixin
from ._mochat_inbound import _MochatInboundMixin
from ._mochat_lifecycle import _MochatLifecycleMixin
from ._mochat_notify import _MochatNotifyMixin
from ._mochat_outbound import _MochatOutboundMixin
from ._mochat_socket import _MochatSocketMixin


class MochatChannel(
    _MochatLifecycleMixin,
    _MochatSocketMixin,
    _MochatCursorMixin,
    _MochatInboundMixin,
    _MochatNotifyMixin,
    _MochatOutboundMixin,
    BaseChannel,
):
    """Mochat channel using socket.io with fallback polling workers."""

    name = "mochat"

    def __init__(self, config: MochatConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: MochatConfig = config
        self._http: httpx.AsyncClient | None = None
        self._socket: Any = None
        self._ws_connected = self._ws_ready = False
        self._transport_mode = "stopped"

        data_path = get_data_path()
        self._state_dir = data_path / "channels" / "mochat"
        self._cursor_path = self._state_dir / "session_cursors.json"
        self._legacy_cursor_path = data_path / "mochat" / "session_cursors.json"
        self._session_cursor: dict[str, int] = {}
        self._cursor_save_task: asyncio.Task[None] | None = None

        self._session_set: set[str] = set()
        self._panel_set: set[str] = set()
        self._auto_discover_sessions = self._auto_discover_panels = False

        self._cold_sessions: set[str] = set()
        self._session_by_converse: dict[str, str] = {}

        self._seen_set: dict[str, set[str]] = {}
        self._seen_queue: dict[str, deque[str]] = {}
        self._delay_states: dict[str, DelayState] = {}

        self._session_fallback_tasks: dict[str, asyncio.Task[None]] = {}
        self._panel_fallback_tasks: dict[str, asyncio.Task[None]] = {}
        self._refresh_task: asyncio.Task[None] | None = None
        self._target_locks: dict[str, asyncio.Lock] = {}

    _str_field = staticmethod(_str_field)
