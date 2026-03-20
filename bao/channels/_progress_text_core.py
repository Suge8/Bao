from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from bao.channels._progress_text_helpers import (
    final_remainder,
    is_minor_tail,
    merge_progress_chunk,
    next_flush_chunk,
    normalize_for_dedup,
    sanitize_progress_chunk,
)
from bao.progress_scope import main_progress_scope_from_tool_scope, normalize_progress_scope


@dataclass(frozen=True)
class ProgressPolicy:
    flush_interval: float = 0.6
    min_chars: int = 24
    hard_chars: int = 72
    max_wait: float = 1.4
    dedup_window: float = 5.0


@dataclass(frozen=True)
class ProgressEvent:
    is_progress: bool
    is_tool_hint: bool
    clear_only: bool = False
    scope: str | None = None

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, Any] | None) -> ProgressEvent:
        if metadata is None:
            return cls(is_progress=False, is_tool_hint=False)
        return cls(
            is_progress=bool(metadata.get("_progress")),
            is_tool_hint=bool(metadata.get("_tool_hint")),
            clear_only=bool(metadata.get("_progress_clear")),
            scope=normalize_progress_scope(metadata.get("_progress_scope")),
        )


class ProgressHandler(Protocol):
    async def handle(self, chat_id: str, text: str, event: ProgressEvent) -> None: ...

    async def flush(
        self,
        chat_id: str,
        *,
        force: bool = False,
        scope: str | None = None,
    ) -> None: ...

    def clear_all(self) -> None: ...


def _state_key(chat_id: str, scope: str | None) -> str:
    return f"{chat_id}|{scope}" if scope else chat_id


def _chat_id_from_state_key(state_key: str) -> str:
    chat_id, _, _scope = state_key.partition("|")
    return chat_id


def _scope_from_state_key(state_key: str) -> str | None:
    _chat_id, sep, scope = state_key.partition("|")
    return scope if sep else None


class IterationBuffer:
    def __init__(self) -> None:
        self._buf: dict[str, str] = {}
        self._sent: dict[str, str] = {}

    def append(self, chat_id: str, text: str) -> None:
        self._buf[chat_id] = self._buf.get(chat_id, "") + text

    def flush(self, chat_id: str) -> str:
        raw = self._buf.pop(chat_id, "")
        if raw:
            self._sent[chat_id] = self._sent.get(chat_id, "") + raw
        return sanitize_progress_chunk(raw).strip()

    def finish(self, chat_id: str, final_text: str) -> tuple[str, str]:
        raw_buf = self._buf.pop(chat_id, "")
        self._sent.pop(chat_id, None)
        flushed = sanitize_progress_chunk(raw_buf).strip()
        remainder = final_remainder(final_text, raw_buf).lstrip("\n\r")
        if is_minor_tail(remainder):
            remainder = ""
        return flushed, remainder

    def is_active(self, chat_id: str) -> bool:
        return chat_id in self._buf or chat_id in self._sent

    def pending_chat_ids(self) -> list[str]:
        return list(self._buf.keys())

    def process(self, chat_id: str, text: str, event: ProgressEvent) -> list[str]:
        if event.is_progress and event.is_tool_hint:
            parts: list[str] = []
            flushed = self.flush(chat_id)
            if flushed:
                parts.append(flushed)
            hint = sanitize_progress_chunk(text).strip()
            if hint:
                parts.append(hint)
            return parts
        if event.is_progress:
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


class ProgressBuffer:
    def __init__(
        self,
        send_fn: Callable[[str, str], Awaitable[None]],
        policy: ProgressPolicy | None = None,
    ) -> None:
        self._send = send_fn
        self._policy = policy or ProgressPolicy()
        self._buf: dict[str, str] = {}
        self._last_time: dict[str, float] = {}
        self._open: dict[str, bool] = {}
        self._sent: dict[str, str] = {}
        self._last_text: dict[str, str] = {}

    async def handle(self, chat_id: str, text: str, event: ProgressEvent) -> None:
        state_key = _state_key(chat_id, event.scope)
        if event.clear_only:
            self._clear_chat(state_key)
            return
        if event.is_progress and not event.is_tool_hint:
            self._append_progress(state_key, text)
            return
        if event.is_progress and event.is_tool_hint:
            await self._handle_tool_hint(state_key, chat_id, text)
            return
        await self._handle_final(state_key, chat_id, text)

    async def flush_all(self) -> None:
        for state_key in list(self._buf):
            await self._flush(state_key, force=True)

    async def flush(self, chat_id: str, *, force: bool = False, scope: str | None = None) -> None:
        await self._flush(_state_key(chat_id, scope), force=force)

    def clear_all(self) -> None:
        self._buf.clear()
        self._open.clear()
        self._sent.clear()
        self._last_text.clear()
        self._last_time.clear()

    def _append_progress(self, state_key: str, text: str) -> None:
        if not text:
            return
        if not self._open.get(state_key, False):
            text = text.lstrip("\n\r\t ")
            self._open[state_key] = True
            self._last_time[state_key] = self._now()
        current = self._sent.get(state_key, "") + self._buf.get(state_key, "")
        merged = merge_progress_chunk(current, text)
        sent_prefix = self._sent.get(state_key, "")
        self._buf[state_key] = merged[len(sent_prefix) :]

    async def _handle_tool_hint(self, state_key: str, chat_id: str, text: str) -> None:
        tool_scope = _scope_from_state_key(state_key)
        main_scope = main_progress_scope_from_tool_scope(tool_scope)
        if main_scope is not None:
            main_state_key = _state_key(chat_id, main_scope)
            await self._flush(main_state_key, force=True)
            self._clear_chat(main_state_key)
        await self._flush(state_key, force=True)
        self._clear_chat(state_key)
        if text:
            await self._send_checked(state_key, chat_id, text)
        self._clear_chat(state_key)

    async def _handle_final(self, state_key: str, chat_id: str, text: str) -> None:
        self._buf.pop(state_key, None)
        self._open[state_key] = False
        sent = self._sent.pop(state_key, "")
        self._last_text.pop(state_key, None)
        if not text:
            return
        outgoing = text
        if sent and text.startswith(sent):
            outgoing = text[len(sent) :].lstrip("\n\r")
        if not is_minor_tail(outgoing):
            await self._send(chat_id, outgoing)

    def _clear_chat(self, state_key: str) -> None:
        self._buf.pop(state_key, None)
        self._open.pop(state_key, None)
        self._sent.pop(state_key, None)
        self._last_text.pop(state_key, None)
        self._last_time.pop(state_key, None)

    @staticmethod
    def _now() -> float:
        return asyncio.get_event_loop().time()

    async def _send_checked(self, state_key: str, chat_id: str, text: str) -> None:
        if not text.strip():
            return
        now = self._now()
        displayed = text.strip()
        normalized = normalize_for_dedup(displayed)
        if (
            self._last_text.get(state_key) == normalized
            and (now - self._last_time.get(state_key, 0)) < self._policy.dedup_window
        ):
            return
        self._last_text[state_key] = normalized
        self._last_time[state_key] = now
        await self._send(chat_id, displayed)

    async def _flush(self, state_key: str, force: bool) -> None:
        text = self._buf.get(state_key, "")
        if not text:
            return
        chat_id = _chat_id_from_state_key(state_key)
        now = self._now()
        last_sent = self._last_time.get(state_key, now)
        if force:
            self._buf[state_key] = ""
            self._last_time[state_key] = now
            await self._send_checked(state_key, chat_id, text)
            self._sent[state_key] = self._sent.get(state_key, "") + text
            return
        while True:
            text = self._buf.get(state_key, "")
            if not text:
                return
            now = self._now()
            waited = now - last_sent
            if len(text) < self._policy.min_chars and waited < self._policy.flush_interval:
                return
            chunk, remainder = next_flush_chunk(
                text,
                waited,
                self._policy.min_chars,
                self._policy.hard_chars,
                self._policy.max_wait,
            )
            if chunk is None:
                return
            self._buf[state_key] = remainder
            self._last_time[state_key] = now
            last_sent = now
            await self._send_checked(state_key, chat_id, chunk)
            self._sent[state_key] = self._sent.get(state_key, "") + chunk
            if not remainder:
                return
