from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from bao.channels._progress_text_core import (
    ProgressEvent,
    ProgressHandler,
    ProgressPolicy,
    _scope_from_state_key,
)
from bao.channels._progress_text_helpers import (
    final_remainder,
    is_minor_tail,
    merge_progress_chunk,
    next_flush_chunk,
    sanitize_progress_chunk,
)
from bao.progress_scope import main_progress_scope_from_tool_scope


def _default_split(text: str) -> list[str]:
    return [text] if text else []


@dataclass(frozen=True)
class EditingProgressOps:
    create: Callable[[str, str], Awaitable[Any]]
    update: Callable[[str, Any, str], Awaitable[Any]]
    split: Callable[[str], list[str]] = _default_split


class EditingProgress(ProgressHandler):
    def __init__(
        self,
        ops: EditingProgressOps,
        policy: ProgressPolicy | None = None,
        *,
        rewrite_final: bool = True,
    ) -> None:
        self._ops = ops
        self._policy = policy or ProgressPolicy()
        self._rewrite_final = rewrite_final
        self._buf: dict[str, str] = {}
        self._last_time: dict[str, float] = {}
        self._open: dict[str, bool] = {}
        self._sent_raw: dict[str, str] = {}
        self._handles: dict[str, list[Any]] = {}
        self._rendered: dict[str, list[str]] = {}

    async def handle(self, chat_id: str, text: str, event: ProgressEvent) -> None:
        state_key = self._state_key(chat_id, event.scope)
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

    async def flush(
        self,
        chat_id: str,
        *,
        force: bool = False,
        scope: str | None = None,
    ) -> None:
        state_key = self._state_key(chat_id, scope)
        text = self._buf.get(state_key, "")
        if not text:
            return
        now = self._now()
        last_sent = self._last_time.get(state_key, now)
        if force:
            self._buf[state_key] = ""
            self._last_time[state_key] = now
            self._sent_raw[state_key] = self._sent_raw.get(state_key, "") + text
            await self._render_full(state_key, chat_id)
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
            self._sent_raw[state_key] = self._sent_raw.get(state_key, "") + chunk
            await self._render_full(state_key, chat_id)
            if not remainder:
                return

    def clear_all(self) -> None:
        self._buf.clear()
        self._last_time.clear()
        self._open.clear()
        self._sent_raw.clear()
        self._handles.clear()
        self._rendered.clear()

    def _append_progress(self, state_key: str, text: str) -> None:
        if not text:
            return
        if not self._open.get(state_key, False):
            text = text.lstrip("\n\r\t ")
            self._open[state_key] = True
            self._last_time[state_key] = self._now()
        current = self._sent_raw.get(state_key, "") + self._buf.get(state_key, "")
        merged = merge_progress_chunk(current, text)
        sent_prefix = self._sent_raw.get(state_key, "")
        self._buf[state_key] = merged[len(sent_prefix) :]

    async def _handle_tool_hint(self, state_key: str, chat_id: str, text: str) -> None:
        tool_scope = _scope_from_state_key(state_key)
        main_scope = main_progress_scope_from_tool_scope(tool_scope)
        if main_scope is not None:
            main_state_key = self._state_key(chat_id, main_scope)
            await self.flush(chat_id, force=True, scope=main_scope)
            self._clear_chat(main_state_key)
        await self.flush(chat_id, force=True, scope=_scope_from_state_key(state_key))
        self._clear_chat(state_key)
        hint = sanitize_progress_chunk(text).strip()
        if not hint:
            return
        await self._render(state_key, chat_id, hint, allow_rewrite=True)
        self._last_time[state_key] = self._now()
        self._clear_chat(state_key)

    async def _handle_final(self, state_key: str, chat_id: str, text: str) -> None:
        self._buf.pop(state_key, None)
        self._open.pop(state_key, None)
        self._last_time.pop(state_key, None)
        final_text = sanitize_progress_chunk(text).strip()
        sent_raw = self._sent_raw.get(state_key, "")
        if not final_text:
            self._clear_chat(state_key)
            return
        if self._rewrite_final or not sent_raw:
            await self._render(state_key, chat_id, final_text, allow_rewrite=True)
            self._clear_chat(state_key)
            return
        outgoing = _append_only_final_tail(final_text, sent_raw)
        if outgoing:
            self._clear_chat(state_key)
            await self._render(state_key, chat_id, outgoing, allow_rewrite=False)
        self._clear_chat(state_key)

    async def _render_full(self, state_key: str, chat_id: str) -> None:
        rendered = sanitize_progress_chunk(self._sent_raw[state_key]).strip()
        if rendered:
            await self._render(state_key, chat_id, rendered, allow_rewrite=False)

    @staticmethod
    def _now() -> float:
        return asyncio.get_event_loop().time()

    async def _render(
        self,
        state_key: str,
        chat_id: str,
        text: str,
        *,
        allow_rewrite: bool,
    ) -> None:
        segments = self._ops.split(text)
        if not segments:
            return
        handles = self._handles.setdefault(state_key, [])
        rendered = self._rendered.setdefault(state_key, [])
        for index, segment in enumerate(segments):
            handle = handles[index] if index < len(handles) else None
            previous = rendered[index] if index < len(rendered) else None
            if handle is None:
                handle = await self._ops.create(chat_id, segment)
                if index < len(handles):
                    handles[index] = handle
                else:
                    handles.append(handle)
            elif previous != segment:
                if not allow_rewrite and previous and not segment.startswith(previous):
                    segment = previous
                else:
                    new_handle = await self._ops.update(chat_id, handle, segment)
                    handles[index] = handle if new_handle is None else new_handle
            if index < len(rendered):
                rendered[index] = segment
            else:
                rendered.append(segment)

    def _clear_chat(self, state_key: str) -> None:
        self._buf.pop(state_key, None)
        self._last_time.pop(state_key, None)
        self._open.pop(state_key, None)
        self._sent_raw.pop(state_key, None)
        self._handles.pop(state_key, None)
        self._rendered.pop(state_key, None)

    @staticmethod
    def _state_key(chat_id: str, scope: str | None) -> str:
        return f"{chat_id}|{scope}" if scope else chat_id


def _append_only_final_tail(final_text: str, sent_raw: str) -> str:
    outgoing = final_remainder(final_text, sent_raw).lstrip("\n\r")
    return "" if is_minor_tail(outgoing) else outgoing
