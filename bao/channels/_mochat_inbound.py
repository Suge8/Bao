"""Mochat inbound processing and cursor persistence helpers."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Any

from loguru import logger

from bao.bus.events import InboundMessage

from ._mochat_common import (
    MAX_SEEN_MESSAGE_IDS,
    DelayState,
    MochatBufferedEntry,
    SyntheticEventSpec,
    _make_synthetic_event,
    _safe_dict,
    _str_field,
    build_buffered_body,
    normalize_mochat_content,
    parse_timestamp,
    resolve_require_mention,
    resolve_was_mentioned,
)


@dataclass(frozen=True)
class _MochatDelayTarget:
    key: str
    target_id: str
    target_kind: str


@dataclass(frozen=True)
class _MochatDispatchPayload:
    target_id: str
    target_kind: str
    entries: list[MochatBufferedEntry]
    was_mentioned: bool


class _MochatInboundMixin:
    @staticmethod
    def _build_entry(
        payload: dict[str, Any],
        event: dict[str, Any],
        author: str,
    ) -> MochatBufferedEntry:
        author_info = _safe_dict(payload.get("authorInfo"))
        return MochatBufferedEntry(
            raw_body=normalize_mochat_content(payload.get("content")) or "[empty message]",
            author=author,
            sender_name=_str_field(author_info, "nickname", "email"),
            sender_username=_str_field(author_info, "agentId"),
            timestamp=parse_timestamp(event.get("timestamp")),
            message_id=_str_field(payload, "messageId"),
            group_id=_str_field(payload, "groupId"),
        )

    async def _session_watch_worker(self, session_id: str) -> None:
        while self._running and self._transport_mode == "fallback":
            try:
                payload = await self._post_json(
                    "/api/claw/sessions/watch",
                    {
                        "sessionId": session_id,
                        "cursor": self._session_cursor.get(session_id, 0),
                        "timeoutMs": self.config.watch_timeout_ms,
                        "limit": self.config.watch_limit,
                    },
                )
                await self._handle_watch_payload(payload, "session")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    "⚠️ Mochat 轮询回退异常 / fallback watch error: {} {}",
                    session_id,
                    exc,
                )
                if await self._wait_stop_or_timeout(max(0.1, self.config.retry_delay_ms / 1000.0)):
                    break

    async def _panel_poll_worker(self, panel_id: str) -> None:
        sleep_s = max(1.0, self.config.refresh_interval_ms / 1000.0)
        while self._running and self._transport_mode == "fallback":
            try:
                response = await self._post_json(
                    "/api/claw/groups/panels/messages",
                    {"panelId": panel_id, "limit": min(100, max(1, self.config.watch_limit))},
                )
                messages = response.get("messages")
                if isinstance(messages, list):
                    for message in reversed(messages):
                        if not isinstance(message, dict):
                            continue
                        event = _make_synthetic_event(
                            SyntheticEventSpec(
                                message_id=str(message.get("messageId") or ""),
                                author=str(message.get("author") or ""),
                                content=message.get("content"),
                                meta=message.get("meta"),
                                group_id=str(response.get("groupId") or ""),
                                converse_id=panel_id,
                                timestamp=message.get("createdAt"),
                                author_info=message.get("authorInfo"),
                            )
                        )
                        await self._process_inbound_event(panel_id, event, "panel")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    "⚠️ Mochat 面板轮询异常 / panel poll error: {} {}",
                    panel_id,
                    exc,
                )
            if await self._wait_stop_or_timeout(sleep_s):
                break

    async def _handle_watch_payload(self, payload: dict[str, Any], target_kind: str) -> None:
        if not isinstance(payload, dict):
            return
        target_id = self._str_field(payload, "sessionId")
        if not target_id:
            return

        lock = self._target_locks.setdefault(f"{target_kind}:{target_id}", asyncio.Lock())
        async with lock:
            previous_cursor = self._session_cursor.get(target_id, 0) if target_kind == "session" else 0
            payload_cursor = payload.get("cursor")
            if target_kind == "session" and isinstance(payload_cursor, int) and payload_cursor >= 0:
                self._mark_session_cursor(target_id, payload_cursor)

            raw_events = payload.get("events")
            if not isinstance(raw_events, list):
                return
            if target_kind == "session" and target_id in self._cold_sessions:
                self._cold_sessions.discard(target_id)
                return

            for event in raw_events:
                if not isinstance(event, dict):
                    continue
                seq = event.get("seq")
                if (
                    target_kind == "session"
                    and isinstance(seq, int)
                    and seq > self._session_cursor.get(target_id, previous_cursor)
                ):
                    self._mark_session_cursor(target_id, seq)
                if event.get("type") == "message.add":
                    await self._process_inbound_event(target_id, event, target_kind)

    async def _process_inbound_event(
        self,
        target_id: str,
        event: dict[str, Any],
        target_kind: str,
    ) -> None:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return

        author = _str_field(payload, "author")
        if not author or (self.config.agent_user_id and author == self.config.agent_user_id):
            return
        if not self.is_allowed(author):
            return

        message_id = _str_field(payload, "messageId")
        seen_key = f"{target_kind}:{target_id}"
        if message_id and self._remember_message_id(seen_key, message_id):
            return

        entry = self._build_entry(payload, event, author)
        group_id = entry.group_id
        is_group = bool(group_id)
        was_mentioned = resolve_was_mentioned(payload, self.config.agent_user_id)
        require_mention = (
            target_kind == "panel"
            and is_group
            and resolve_require_mention(self.config, target_id, group_id)
        )
        use_delay = target_kind == "panel" and self.config.reply_delay_mode == "non-mention"

        if require_mention and not was_mentioned and not use_delay:
            return

        if use_delay:
            delay_target = _MochatDelayTarget(
                key=seen_key,
                target_id=target_id,
                target_kind=target_kind,
            )
            if was_mentioned:
                await self._flush_delayed_entries(delay_target, "mention", entry)
            else:
                await self._enqueue_delayed_entry(delay_target, entry)
            return

        await self._dispatch_entries(
            _MochatDispatchPayload(
                target_id=target_id,
                target_kind=target_kind,
                entries=[entry],
                was_mentioned=was_mentioned,
            )
        )

    def _remember_message_id(self, key: str, message_id: str) -> bool:
        seen_set = self._seen_set.setdefault(key, set())
        seen_queue = self._seen_queue.setdefault(key, deque())
        if message_id in seen_set:
            return True
        seen_set.add(message_id)
        seen_queue.append(message_id)
        while len(seen_queue) > MAX_SEEN_MESSAGE_IDS:
            seen_set.discard(seen_queue.popleft())
        return False

    async def _enqueue_delayed_entry(self, target: _MochatDelayTarget, entry: MochatBufferedEntry) -> None:
        state = self._delay_states.setdefault(target.key, DelayState())
        async with state.lock:
            state.entries.append(entry)
            if state.timer:
                state.timer.cancel()
            state.timer = asyncio.create_task(self._delay_flush_after(target))

    async def _delay_flush_after(self, target: _MochatDelayTarget) -> None:
        await asyncio.sleep(max(0, self.config.reply_delay_ms) / 1000.0)
        await self._flush_delayed_entries(target, "timer", None)

    async def _flush_delayed_entries(
        self,
        target: _MochatDelayTarget,
        reason: str,
        entry: MochatBufferedEntry | None,
    ) -> None:
        state = self._delay_states.setdefault(target.key, DelayState())
        async with state.lock:
            if entry:
                state.entries.append(entry)
            current = asyncio.current_task()
            if state.timer and state.timer is not current:
                state.timer.cancel()
            state.timer = None
            entries = state.entries[:]
            state.entries.clear()
        if entries:
            await self._dispatch_entries(
                _MochatDispatchPayload(
                    target_id=target.target_id,
                    target_kind=target.target_kind,
                    entries=entries,
                    was_mentioned=reason == "mention",
                )
            )

    async def _dispatch_entries(self, payload: _MochatDispatchPayload) -> None:
        if not payload.entries:
            return
        last = payload.entries[-1]
        is_group = bool(last.group_id)
        body = build_buffered_body(payload.entries, is_group) or "[empty message]"
        await self._handle_message(
            InboundMessage(
                channel=self.name,
                sender_id=last.author,
                chat_id=payload.target_id,
                content=body,
                metadata={
                    "message_id": last.message_id,
                    "timestamp": last.timestamp,
                    "is_group": is_group,
                    "group_id": last.group_id,
                    "sender_name": last.sender_name,
                    "sender_username": last.sender_username,
                    "target_kind": payload.target_kind,
                    "was_mentioned": payload.was_mentioned,
                    "buffered_count": len(payload.entries),
                },
            )
        )

    async def _cancel_delay_timers(self) -> None:
        for state in self._delay_states.values():
            if state.timer:
                state.timer.cancel()
        self._delay_states.clear()
