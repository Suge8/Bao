"""Shared DingTalk outbound payload types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DingTalkUploadRequest:
    token: str
    data: bytes
    media_type: str
    filename: str
    content_type: str | None


@dataclass(frozen=True)
class DingTalkSendRequest:
    token: str
    chat_id: str
    msg_key: str
    msg_param: dict[str, Any]
