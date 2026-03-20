"""Discord inbound helpers."""

from __future__ import annotations

from typing import Any

from loguru import logger

from bao.bus.events import InboundMessage

from ._discord_common import MAX_ATTACHMENT_BYTES


class _DiscordInboundMixin:
    async def _handle_message_create(self, payload: dict[str, Any]) -> None:
        author = payload.get("author") or {}
        if author.get("bot"):
            return

        sender_id = str(author.get("id", ""))
        channel_id = str(payload.get("channel_id", ""))
        content = payload.get("content") or ""
        guild_id = payload.get("guild_id")
        if not sender_id or not channel_id:
            return
        if not self.is_allowed(sender_id):
            return
        if guild_id is not None and not self._should_respond_in_group(payload, content):
            return

        content_parts, media_paths = await self._build_message_payload(payload, content)
        reply_to = str(payload.get("id") or "")
        referenced_message_id = (payload.get("referenced_message") or {}).get("id")

        await self._start_typing(channel_id)
        await self._handle_message(
            InboundMessage(
                channel=self.name,
                sender_id=sender_id,
                chat_id=channel_id,
                content="\n".join(part for part in content_parts if part) or "[empty message]",
                media=media_paths,
                metadata={
                    "message_id": str(payload.get("id", "")),
                    "guild_id": guild_id,
                    "reply_to": reply_to or None,
                    "referenced_message_id": str(referenced_message_id) if referenced_message_id else None,
                },
            )
        )

    async def _build_message_payload(
        self,
        payload: dict[str, Any],
        content: str,
    ) -> tuple[list[str], list[str]]:
        from . import discord as discord_module

        content_parts = [content] if content else []
        media_paths: list[str] = []
        media_dir = discord_module.get_media_dir("discord")

        for attachment in payload.get("attachments") or []:
            file_result = await self._download_attachment(attachment, media_dir)
            if file_result is None:
                continue
            saved_path, content_part = file_result
            if saved_path:
                media_paths.append(saved_path)
            if content_part:
                content_parts.append(content_part)
        return content_parts, media_paths

    async def _download_attachment(
        self,
        attachment: dict[str, Any],
        media_dir,
    ) -> tuple[str | None, str | None] | None:
        url = attachment.get("url")
        filename = attachment.get("filename") or "attachment"
        size = attachment.get("size") or 0
        if not url or not self._http:
            return None
        if size and size > MAX_ATTACHMENT_BYTES:
            return None, f"[attachment: {filename} - too large]"
        try:
            media_dir.mkdir(parents=True, exist_ok=True)
            file_path = media_dir / f"{attachment.get('id', 'file')}_{filename.replace('/', '_')}"
            response = await self._http.get(url)
            response.raise_for_status()
            file_path.write_bytes(response.content)
            return str(file_path), f"[attachment: {file_path}]"
        except Exception as exc:
            logger.warning("⚠️ 下载失败 / attachment failed: {}", exc)
            return None, f"[attachment: {filename} - download failed]"

    def _should_respond_in_group(self, payload: dict[str, Any], content: str) -> bool:
        if self.config.group_policy == "open":
            return True

        bot_user_id = self._bot_user_id
        if bot_user_id:
            for mention in payload.get("mentions") or []:
                if str(mention.get("id")) == bot_user_id:
                    return True
            if f"<@{bot_user_id}>" in content or f"<@!{bot_user_id}>" in content:
                return True

        logger.debug("Discord message in {} ignored (bot not mentioned)", payload.get("channel_id"))
        return False
