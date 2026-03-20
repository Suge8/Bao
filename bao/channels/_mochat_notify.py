"""Mochat notify event helpers."""

from __future__ import annotations

from typing import Any

from ._mochat_common import SyntheticEventSpec, _make_synthetic_event, _str_field


class _MochatNotifyMixin:
    async def _handle_notify_chat_message(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        group_id = _str_field(payload, "groupId")
        panel_id = _str_field(payload, "converseId", "panelId")
        if not group_id or not panel_id:
            return
        if self._panel_set and panel_id not in self._panel_set:
            return

        event = _make_synthetic_event(
            SyntheticEventSpec(
                message_id=str(payload.get("_id") or payload.get("messageId") or ""),
                author=str(payload.get("author") or ""),
                content=payload.get("content"),
                meta=payload.get("meta"),
                group_id=group_id,
                converse_id=panel_id,
                timestamp=payload.get("createdAt"),
                author_info=payload.get("authorInfo"),
            )
        )
        await self._process_inbound_event(panel_id, event, "panel")

    async def _handle_notify_inbox_append(self, payload: Any) -> None:
        if not isinstance(payload, dict) or payload.get("type") != "message":
            return
        detail = payload.get("payload")
        if not isinstance(detail, dict) or _str_field(detail, "groupId"):
            return
        converse_id = _str_field(detail, "converseId")
        if not converse_id:
            return

        session_id = self._session_by_converse.get(converse_id)
        if not session_id:
            await self._refresh_sessions_directory(self._transport_mode == "socket")
            session_id = self._session_by_converse.get(converse_id)
        if not session_id:
            return

        event = _make_synthetic_event(
            SyntheticEventSpec(
                message_id=str(detail.get("messageId") or payload.get("_id") or ""),
                author=str(detail.get("messageAuthor") or ""),
                content=str(detail.get("messagePlainContent") or detail.get("messageSnippet") or ""),
                meta={"source": "notify:chat.inbox.append", "converseId": converse_id},
                group_id="",
                converse_id=converse_id,
                timestamp=payload.get("createdAt"),
            )
        )
        await self._process_inbound_event(session_id, event, "session")
