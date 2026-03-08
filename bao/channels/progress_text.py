from __future__ import annotations

import asyncio
import re
from typing import Any, Awaitable, Callable, Protocol


def sanitize_progress_chunk(text: str) -> str:
    value = text.replace("\r\n", "\n").replace("\r", "\n")
    value = value.lstrip("\n")
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value


def common_prefix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def final_remainder(final_text: str, streamed_text: str) -> str:
    if not streamed_text:
        return final_text
    start = common_prefix_len(final_text, streamed_text)
    overlap_ratio = start / max(1, len(final_text))
    if overlap_ratio < 0.6:
        return final_text
    return final_text[start:]


def is_minor_tail(text: str) -> bool:
    if len(text) > 3:
        return False
    stripped = text.strip()
    if not stripped:
        return True
    return all(ch in "。！？!?，,；;:：、.\n\r\t " for ch in stripped)


class IterationBuffer:
    """Buffer token-level progress, flush at iteration boundaries (tool hints / final)."""

    def __init__(self) -> None:
        self._buf: dict[str, str] = {}
        self._sent: dict[str, str] = {}

    def append(self, chat_id: str, text: str) -> None:
        self._buf[chat_id] = self._buf.get(chat_id, "") + text

    def flush(self, chat_id: str) -> str:
        """Flush buffer, return sanitized text to send. Tracks as sent."""
        raw = self._buf.pop(chat_id, "")
        if raw:
            self._sent[chat_id] = self._sent.get(chat_id, "") + raw
        cleaned = sanitize_progress_chunk(raw)
        return cleaned.strip()

    def finish(self, chat_id: str, final_text: str) -> tuple[str, str]:
        """Final arrived. Returns (flushed_buf, remainder). Resets state."""
        raw_buf = self._buf.pop(chat_id, "")
        self._sent.pop(chat_id, None)
        flushed = sanitize_progress_chunk(raw_buf).strip()
        rem = final_remainder(final_text, raw_buf).lstrip("\n\r")
        if is_minor_tail(rem):
            rem = ""
        return flushed, rem

    def is_active(self, chat_id: str) -> bool:
        return chat_id in self._buf or chat_id in self._sent

    def pending_chat_ids(self) -> list[str]:
        return list(self._buf.keys())

    def process(
        self, chat_id: str, text: str, *, is_progress: bool, is_tool_hint: bool
    ) -> list[str]:
        """Route a message through the buffer. Returns list of texts to send."""
        if is_progress and is_tool_hint:
            parts: list[str] = []
            flushed = self.flush(chat_id)
            if flushed:
                parts.append(flushed)
            hint = sanitize_progress_chunk(text).strip()
            if hint:
                parts.append(hint)
            return parts
        if is_progress:
            clean = text.lstrip("\n\r\t ") if not self.is_active(chat_id) else text
            if clean:
                self.append(chat_id, clean)
            return []
        if self.is_active(chat_id):
            flushed, remainder = self.finish(chat_id, text)
            parts = []
            if flushed:
                parts.append(flushed)
            if remainder:
                parts.append(remainder)
            return parts
        return [text]


def _normalize_for_dedup(text: str) -> str:
    """Normalize text for dedup comparison: collapse whitespace."""
    return " ".join(text.split())


class ProgressHandler(Protocol):
    async def handle(
        self,
        chat_id: str,
        text: str,
        *,
        is_progress: bool,
        is_tool_hint: bool,
        clear_only: bool = False,
    ) -> None: ...

    async def flush(self, chat_id: str, *, force: bool = False) -> None: ...

    def clear_all(self) -> None: ...


def _next_flush_chunk(
    text: str,
    *,
    waited: float,
    min_chars: int,
    hard_chars: int,
    max_wait: float,
) -> tuple[str | None, str]:
    boundary = ProgressBuffer._last_boundary(text)
    if boundary >= 0 and (boundary + 1 >= min_chars or waited >= max_wait):
        return text[: boundary + 1], text[boundary + 1 :]
    if len(text) >= hard_chars:
        split_at = ProgressBuffer._last_soft_split(text, hard_chars)
        if split_at < min_chars:
            split_at = hard_chars - 1
        return text[: split_at + 1], text[split_at + 1 :]
    if waited >= max_wait and len(text) >= min_chars:
        return text, ""
    return None, text


class ProgressBuffer:
    """
    Buffers progress tokens for non-streaming channels.

    Features:
    - Sentence-boundary flushing (same as iMessage's original logic)
    - Cross-iteration dedup: skips sending if normalized text matches last sent within window
    """

    def __init__(
        self,
        send_fn: "Callable[[str, str], Awaitable[None]]",
        *,
        flush_interval: float = 0.6,
        min_chars: int = 24,
        hard_chars: int = 72,
        max_wait: float = 1.4,
        dedup_window: float = 5.0,
    ) -> None:
        self._send = send_fn
        self._buf: dict[str, str] = {}
        self._last_time: dict[str, float] = {}
        self._open: dict[str, bool] = {}
        self._sent: dict[str, str] = {}
        self._last_text: dict[str, str] = {}  # dedup: normalized last-sent
        self._flush_interval = flush_interval
        self._min_chars = min_chars
        self._hard_chars = hard_chars
        self._max_wait = max_wait
        self._dedup_window = dedup_window

    # -- public API --

    async def handle(
        self,
        chat_id: str,
        text: str,
        *,
        is_progress: bool,
        is_tool_hint: bool,
        clear_only: bool = False,
    ) -> None:
        """Route an outbound message through buffer + dedup."""
        if clear_only:
            self._clear_chat(chat_id)
            return

        if is_progress and not is_tool_hint:
            if not text:
                return
            # Accumulate progress tokens
            if not self._open.get(chat_id, False):
                text = text.lstrip("\n\r\t ")
                self._open[chat_id] = True
                self._last_time[chat_id] = self._now()
            self._buf[chat_id] = self._buf.get(chat_id, "") + text
            return

        if is_progress and is_tool_hint:
            await self._flush(chat_id, force=True)
            self._clear_chat(chat_id)
            if text:
                await self._send_checked(chat_id, text)
            self._clear_chat(chat_id)
            return

        self._buf.pop(chat_id, None)
        self._open[chat_id] = False
        sent = self._sent.pop(chat_id, "")
        self._last_text.pop(chat_id, None)
        if text:
            outgoing = text
            if sent and text.startswith(sent):
                outgoing = text[len(sent) :].lstrip("\n\r")
            if not is_minor_tail(outgoing):
                await self._send(chat_id, outgoing)

    async def flush_all(self) -> None:
        """Force-flush all active buffers (call on channel stop)."""
        for chat_id in list(self._buf):
            await self._flush(chat_id, force=True)

    async def flush(self, chat_id: str, *, force: bool = False) -> None:
        await self._flush(chat_id, force=force)

    def clear_all(self) -> None:
        self._buf.clear()
        self._open.clear()
        self._sent.clear()
        self._last_text.clear()
        self._last_time.clear()

    def _clear_chat(self, chat_id: str) -> None:
        self._buf.pop(chat_id, None)
        self._open.pop(chat_id, None)
        self._sent.pop(chat_id, None)
        self._last_text.pop(chat_id, None)
        self._last_time.pop(chat_id, None)

    # -- internals --

    @staticmethod
    def _now() -> float:
        return asyncio.get_event_loop().time()

    async def _send_checked(self, chat_id: str, text: str) -> None:
        """Send text, skipping if it's a duplicate within the dedup window."""
        if not text.strip():
            return
        now = self._now()
        displayed = text.strip()
        normalized = _normalize_for_dedup(displayed)
        if (
            self._last_text.get(chat_id) == normalized
            and (now - self._last_time.get(chat_id, 0)) < self._dedup_window
        ):
            return
        self._last_text[chat_id] = normalized
        self._last_time[chat_id] = now
        await self._send(chat_id, displayed)
        self._sent[chat_id] = self._sent.get(chat_id, "") + text

    @staticmethod
    def _last_boundary(text: str) -> int:
        chars = ("\n", "。", ".", "!", "?", "！", "？", "，", ",", "；", ";")
        return max(text.rfind(ch) for ch in chars)

    @staticmethod
    def _last_soft_split(text: str, limit: int) -> int:
        window = text[:limit]
        return max(window.rfind(ch) for ch in (" ", "，", ",", "、", "/", ")", "]", "}"))

    async def _flush(self, chat_id: str, force: bool) -> None:
        text = self._buf.get(chat_id, "")
        if not text:
            return

        now = self._now()
        last_sent = self._last_time.get(chat_id, now)

        if force:
            self._buf[chat_id] = ""
            self._last_time[chat_id] = now
            await self._send_checked(chat_id, text)
            return

        while True:
            text = self._buf.get(chat_id, "")
            if not text:
                return

            now = self._now()
            waited = now - last_sent
            if len(text) < self._min_chars and waited < self._flush_interval:
                return
            chunk, remainder = _next_flush_chunk(
                text,
                waited=waited,
                min_chars=self._min_chars,
                hard_chars=self._hard_chars,
                max_wait=self._max_wait,
            )
            if chunk is not None:
                self._buf[chat_id] = remainder
                self._last_time[chat_id] = now
                last_sent = now
                await self._send_checked(chat_id, chunk)
                if remainder:
                    continue
                return
            return


class EditingProgress:
    def __init__(
        self,
        create_fn: "Callable[[str, str], Awaitable[Any]]",
        update_fn: "Callable[[str, Any, str], Awaitable[Any]]",
        send_fn: "Callable[[str, str], Awaitable[None]]",
        *,
        split_fn: "Callable[[str], list[str]] | None" = None,
        flush_interval: float = 0.6,
        min_chars: int = 24,
        hard_chars: int = 72,
        max_wait: float = 1.4,
    ) -> None:
        self._create = create_fn
        self._update = update_fn
        self._send = send_fn
        self._split = split_fn or (lambda text: [text] if text else [])
        self._buf: dict[str, str] = {}
        self._last_time: dict[str, float] = {}
        self._open: dict[str, bool] = {}
        self._sent_raw: dict[str, str] = {}
        self._handles: dict[str, list[Any]] = {}
        self._rendered: dict[str, list[str]] = {}
        self._flush_interval = flush_interval
        self._min_chars = min_chars
        self._hard_chars = hard_chars
        self._max_wait = max_wait

    async def handle(
        self,
        chat_id: str,
        text: str,
        *,
        is_progress: bool,
        is_tool_hint: bool,
        clear_only: bool = False,
    ) -> None:
        if clear_only:
            self._clear_chat(chat_id)
            return

        if is_progress and not is_tool_hint:
            if not text:
                return
            if not self._open.get(chat_id, False):
                text = text.lstrip("\n\r\t ")
                self._open[chat_id] = True
                self._last_time[chat_id] = self._now()
            self._buf[chat_id] = self._buf.get(chat_id, "") + text
            return

        if is_progress and is_tool_hint:
            await self.flush(chat_id, force=True)
            self._clear_chat(chat_id, keep_handles=False)
            hint = sanitize_progress_chunk(text).strip()
            if hint:
                await self._render(chat_id, hint)
                self._last_time[chat_id] = self._now()
                self._clear_chat(chat_id, keep_handles=False)
            return

        self._buf.pop(chat_id, None)
        self._open.pop(chat_id, None)
        self._last_time.pop(chat_id, None)
        final_text = sanitize_progress_chunk(text).strip()
        if final_text:
            await self._render(chat_id, final_text)
        self._clear_chat(chat_id, keep_handles=False)

    async def flush(self, chat_id: str, *, force: bool = False) -> None:
        text = self._buf.get(chat_id, "")
        if not text:
            return

        now = self._now()
        last_sent = self._last_time.get(chat_id, now)

        if force:
            self._buf[chat_id] = ""
            self._last_time[chat_id] = now
            self._sent_raw[chat_id] = self._sent_raw.get(chat_id, "") + text
            rendered = sanitize_progress_chunk(self._sent_raw[chat_id]).strip()
            if rendered:
                await self._render(chat_id, rendered)
            return

        while True:
            text = self._buf.get(chat_id, "")
            if not text:
                return

            now = self._now()
            waited = now - last_sent
            if len(text) < self._min_chars and waited < self._flush_interval:
                return

            chunk, remainder = _next_flush_chunk(
                text,
                waited=waited,
                min_chars=self._min_chars,
                hard_chars=self._hard_chars,
                max_wait=self._max_wait,
            )
            if chunk is None:
                return

            self._buf[chat_id] = remainder
            self._last_time[chat_id] = now
            last_sent = now
            self._sent_raw[chat_id] = self._sent_raw.get(chat_id, "") + chunk
            rendered = sanitize_progress_chunk(self._sent_raw[chat_id]).strip()
            if rendered:
                await self._render(chat_id, rendered)
            if remainder:
                continue
            return

    def clear_all(self) -> None:
        self._buf.clear()
        self._last_time.clear()
        self._open.clear()
        self._sent_raw.clear()
        self._handles.clear()
        self._rendered.clear()

    @staticmethod
    def _now() -> float:
        return asyncio.get_event_loop().time()

    async def _render(self, chat_id: str, text: str) -> None:
        segments = self._split(text)
        if not segments:
            return

        handles = self._handles.setdefault(chat_id, [])
        rendered = self._rendered.setdefault(chat_id, [])
        for idx, segment in enumerate(segments):
            handle = handles[idx] if idx < len(handles) else None
            previous = rendered[idx] if idx < len(rendered) else None
            if handle is None:
                new_handle = await self._create(chat_id, segment)
                if idx < len(handles):
                    handles[idx] = new_handle
                else:
                    handles.append(new_handle)
            elif previous != segment:
                new_handle = await self._update(chat_id, handle, segment)
                handles[idx] = handle if new_handle is None else new_handle

            if idx < len(rendered):
                rendered[idx] = segment
            else:
                rendered.append(segment)

    def _clear_chat(self, chat_id: str, *, keep_handles: bool = False) -> None:
        self._buf.pop(chat_id, None)
        self._last_time.pop(chat_id, None)
        self._open.pop(chat_id, None)
        self._sent_raw.pop(chat_id, None)
        if not keep_handles:
            self._handles.pop(chat_id, None)
            self._rendered.pop(chat_id, None)
