from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Literal

DEFAULT_TRANSCRIPT_LIMIT = 200
_CURSOR_VERSION = 1
_REF_VERSION = 1

TranscriptMode = Literal["tail", "range", "full"]


def _encode_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_payload(value: str) -> dict[str, Any] | None:
    text = str(value or "").strip()
    if not text:
        return None
    padding = "=" * (-len(text) % 4)
    try:
        raw = base64.urlsafe_b64decode(f"{text}{padding}".encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def encode_transcript_cursor(offset: int) -> str:
    return _encode_payload({"v": _CURSOR_VERSION, "offset": max(0, int(offset))})


def decode_transcript_cursor(cursor: str) -> int | None:
    payload = _decode_payload(cursor)
    if payload is None or payload.get("v") != _CURSOR_VERSION:
        return None
    offset = payload.get("offset")
    if isinstance(offset, bool):
        return None
    if isinstance(offset, int):
        return max(0, offset)
    if isinstance(offset, float):
        return max(0, int(offset))
    if isinstance(offset, str) and offset.strip().isdigit():
        return max(0, int(offset.strip()))
    return None


def build_transcript_ref(session_key: str, updated_at: str, total_messages: int) -> str:
    return _encode_payload(
        {
            "v": _REF_VERSION,
            "session_key": str(session_key or ""),
            "updated_at": str(updated_at or ""),
            "total_messages": max(0, int(total_messages)),
        }
    )


@dataclass(frozen=True)
class TranscriptReadRequest:
    mode: TranscriptMode = "tail"
    limit: int = DEFAULT_TRANSCRIPT_LIMIT
    cursor: str = ""
    transcript_ref: str = ""

    def normalized_limit(self) -> int:
        if self.mode == "full":
            return 0
        value = int(self.limit or 0)
        return value if value > 0 else DEFAULT_TRANSCRIPT_LIMIT


@dataclass(frozen=True)
class TranscriptPage:
    session_key: str
    mode: TranscriptMode
    transcript_ref: str
    total_messages: int
    start_offset: int
    end_offset: int
    messages: list[dict[str, Any]]
    previous_cursor: str = ""
    next_cursor: str = ""
    has_more_before: bool = False
    has_more_after: bool = False
