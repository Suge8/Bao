from __future__ import annotations

import re

_SQUEEZE_BLANK_LINES = re.compile(r"\n{3,}")
_MINOR_TAIL_CHARS = "。！？!?，,；;:：、.\n\r\t "
_BOUNDARY_CHARS = ("\n", "。", ".", "!", "?", "！", "？", "，", ",", "；", ";")
_SOFT_SPLIT_CHARS = (" ", "，", ",", "、", "/", ")", "]", "}")
_SNAPSHOT_REWRITE_PREFIX_RATIO = 0.4
_SNAPSHOT_REWRITE_PREFIX_MIN_CHARS = 2


def sanitize_progress_chunk(text: str) -> str:
    value = text.replace("\r\n", "\n").replace("\r", "\n")
    value = value.lstrip("\n")
    return _SQUEEZE_BLANK_LINES.sub("\n\n", value)


def common_prefix_len(a: str, b: str) -> int:
    limit = min(len(a), len(b))
    index = 0
    while index < limit and a[index] == b[index]:
        index += 1
    return index


def final_remainder(final_text: str, streamed_text: str) -> str:
    if not streamed_text:
        return final_text
    start = common_prefix_len(final_text, streamed_text)
    overlap_ratio = start / max(1, len(final_text))
    if overlap_ratio < 0.6:
        return final_text
    return final_text[start:]


def merge_progress_chunk(streamed_text: str, incoming_text: str) -> str:
    if not incoming_text:
        return streamed_text
    if not streamed_text:
        return incoming_text
    if incoming_text.startswith(streamed_text):
        return incoming_text
    if streamed_text.startswith(incoming_text):
        return streamed_text
    shared_prefix = common_prefix_len(streamed_text, incoming_text)
    if shared_prefix:
        shared_ratio = shared_prefix / max(1, min(len(streamed_text), len(incoming_text)))
        if (
            shared_prefix >= _SNAPSHOT_REWRITE_PREFIX_MIN_CHARS
            and shared_ratio >= _SNAPSHOT_REWRITE_PREFIX_RATIO
        ):
            return streamed_text
    return streamed_text + incoming_text


def is_minor_tail(text: str) -> bool:
    if len(text) > 3:
        return False
    stripped = text.strip()
    if not stripped:
        return True
    return all(char in _MINOR_TAIL_CHARS for char in stripped)


def normalize_for_dedup(text: str) -> str:
    return " ".join(text.split())


def next_flush_chunk(text: str, waited: float, min_chars: int, hard_chars: int, max_wait: float) -> tuple[str | None, str]:
    boundary = max(text.rfind(char) for char in _BOUNDARY_CHARS)
    if boundary >= 0 and (boundary + 1 >= min_chars or waited >= max_wait):
        return text[: boundary + 1], text[boundary + 1 :]
    if len(text) >= hard_chars:
        split_at = max(text[:hard_chars].rfind(char) for char in _SOFT_SPLIT_CHARS)
        if split_at < min_chars:
            split_at = hard_chars - 1
        return text[: split_at + 1], text[split_at + 1 :]
    if waited >= max_wait and len(text) >= min_chars:
        return text, ""
    return None, text
