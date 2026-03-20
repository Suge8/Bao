from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ReplyRouteInput:
    channel: str = ""
    chat_id: str = ""
    session_key: str | None = None
    lang: str = "en"
    message_id: str | int | None = None
    reply_metadata: dict[str, Any] = field(default_factory=dict)
