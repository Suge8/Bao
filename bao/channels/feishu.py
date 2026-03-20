"""Feishu/Lark channel implementation using lark-oapi SDK with WebSocket long connection."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from typing import Any

from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.channels.progress_text import EditingProgress, EditingProgressOps
from bao.config.paths import get_media_dir
from bao.config.schema import FeishuConfig

from . import _feishu_extract as _feishu_extract
from . import _feishu_sdk as _feishu_sdk
from ._feishu_format import _FeishuFormatMixin
from ._feishu_inbound import _FeishuInboundMixin
from ._feishu_lifecycle import _FeishuLifecycleMixin
from ._feishu_media import _FeishuMediaMixin
from ._feishu_outbound import _FeishuOutboundMixin

_extract_interactive_content = _feishu_extract._extract_interactive_content
_extract_post_text = _feishu_extract._extract_post_text
FEISHU_AVAILABLE = _feishu_sdk.FEISHU_AVAILABLE
lark = _feishu_sdk.lark
CreateFileRequest = _feishu_sdk.CreateFileRequest
CreateFileRequestBody = _feishu_sdk.CreateFileRequestBody
CreateImageRequest = _feishu_sdk.CreateImageRequest
CreateImageRequestBody = _feishu_sdk.CreateImageRequestBody
CreateMessageReactionRequest = _feishu_sdk.CreateMessageReactionRequest
CreateMessageReactionRequestBody = _feishu_sdk.CreateMessageReactionRequestBody
CreateMessageRequest = _feishu_sdk.CreateMessageRequest
CreateMessageRequestBody = _feishu_sdk.CreateMessageRequestBody
Emoji = _feishu_sdk.Emoji
GetFileRequest = _feishu_sdk.GetFileRequest
GetMessageResourceRequest = _feishu_sdk.GetMessageResourceRequest
PatchMessageRequest = _feishu_sdk.PatchMessageRequest
PatchMessageRequestBody = _feishu_sdk.PatchMessageRequestBody

__all__ = [
    "FEISHU_AVAILABLE",
    "FeishuChannel",
    "CreateFileRequest",
    "CreateFileRequestBody",
    "CreateImageRequest",
    "CreateImageRequestBody",
    "CreateMessageReactionRequest",
    "CreateMessageReactionRequestBody",
    "CreateMessageRequest",
    "CreateMessageRequestBody",
    "Emoji",
    "GetFileRequest",
    "GetMessageResourceRequest",
    "PatchMessageRequest",
    "PatchMessageRequestBody",
    "get_media_dir",
    "lark",
    "_extract_interactive_content",
    "_extract_post_text",
]


class FeishuChannel(
    _FeishuLifecycleMixin,
    _FeishuFormatMixin,
    _FeishuMediaMixin,
    _FeishuOutboundMixin,
    _FeishuInboundMixin,
    BaseChannel,
):
    """Feishu/Lark channel using WebSocket long connection."""

    name = "feishu"

    def __init__(self, config: FeishuConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: FeishuConfig = config
        self._client: Any = None
        self._ws_client: Any = None
        self._ws_thread: Any = None
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()  # Ordered dedup cache
        self._loop: asyncio.AbstractEventLoop | None = None
        self._progress_handler = EditingProgress(
            EditingProgressOps(
                create=self._create_progress_text,
                update=self._update_progress_text,
            )
        )
