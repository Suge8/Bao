"""DingTalk/DingDing channel implementation using Stream Mode."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.channels.progress_text import ProgressBuffer
from bao.config.schema import DingTalkConfig

from . import _dingtalk_common as _dingtalk_common
from ._dingtalk_inbound import _DingTalkInboundMixin
from ._dingtalk_lifecycle import _DingTalkLifecycleMixin
from ._dingtalk_outbound import _DingTalkOutboundMixin

DINGTALK_AVAILABLE = _dingtalk_common.DINGTALK_AVAILABLE


class DingTalkChannel(
    _DingTalkLifecycleMixin,
    _DingTalkOutboundMixin,
    _DingTalkInboundMixin,
    BaseChannel,
):
    """DingTalk channel using Stream Mode."""

    name = "dingtalk"
    _IMAGE_EXTS = _dingtalk_common.DINGTALK_IMAGE_EXTS
    _AUDIO_EXTS = _dingtalk_common.DINGTALK_AUDIO_EXTS
    _VIDEO_EXTS = _dingtalk_common.DINGTALK_VIDEO_EXTS

    _is_http_url = staticmethod(_dingtalk_common._is_http_url)
    _extract_message_content = staticmethod(_dingtalk_common._extract_message_content)
    _extract_conversation = staticmethod(_dingtalk_common._extract_conversation)
    _resolve_local_media_path = staticmethod(_dingtalk_common._resolve_local_media_path)
    _build_chat_id = staticmethod(_dingtalk_common._build_chat_id)
    _build_metadata = staticmethod(_dingtalk_common._build_metadata)

    def __init__(self, config: DingTalkConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: DingTalkConfig = config
        self._client: Any = None
        self._http: httpx.AsyncClient | None = None

        # Access Token management for sending messages
        self._access_token: str | None = None
        self._token_expiry: float = 0
        self._progress_token: str | None = None

        # Hold references to background tasks to prevent GC
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._progress_handler = ProgressBuffer(self._send_text)

    def _guess_upload_type(self, media_ref: str) -> str:
        return _dingtalk_common._guess_upload_type(media_ref)

    def _guess_filename(self, media_ref: str, upload_type: str) -> str:
        return _dingtalk_common._guess_filename(media_ref, upload_type)
