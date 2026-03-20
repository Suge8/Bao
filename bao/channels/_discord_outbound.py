"""Discord outbound helpers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from loguru import logger

from bao.bus.events import OutboundMessage

from ._discord_common import DISCORD_API_BASE, MAX_ATTACHMENT_BYTES


class _DiscordOutboundMixin:
    async def send(self, msg: OutboundMessage) -> None:
        if not self._http:
            logger.warning("⚠️ 未初始化 / client not initialized: Discord HTTP")
            return

        sent_media = False
        failed_media: list[str] = []
        for media_path in msg.media or []:
            if await self._send_file(msg.chat_id, media_path, reply_to=msg.reply_to):
                sent_media = True
            else:
                failed_media.append(Path(media_path).name)

        dispatch_msg = self._build_dispatch_message(msg, sent_media, failed_media)
        self._progress_reply_to[msg.chat_id] = msg.reply_to if not sent_media else None

        try:
            await self._dispatch_progress_text(dispatch_msg, flush_progress=True)
            meta = dispatch_msg.metadata or {}
            if bool(meta.get("_progress_clear")) or not bool(meta.get("_progress")):
                self._progress_reply_to.pop(msg.chat_id, None)
        finally:
            await self._stop_typing(msg.chat_id)

    @staticmethod
    def _build_dispatch_message(
        msg: OutboundMessage,
        sent_media: bool,
        failed_media: list[str],
    ) -> OutboundMessage:
        if msg.content or not failed_media or sent_media:
            return msg
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content="\n".join(f"[attachment: {name} - send failed]" for name in failed_media),
            reply_to=msg.reply_to,
            media=[],
            metadata=dict(msg.metadata),
        )

    async def _send_text(self, chat_id: str, text: str) -> None:
        url = f"{DISCORD_API_BASE}/channels/{chat_id}/messages"
        await self._send_payload(url, self._build_text_payload(chat_id, text))

    async def _create_progress_text(self, chat_id: str, text: str) -> str | None:
        url = f"{DISCORD_API_BASE}/channels/{chat_id}/messages"
        response = await self._send_payload(url, self._build_text_payload(chat_id, text))
        return str(response.get("id", "")) if response else None

    def _build_text_payload(self, chat_id: str, text: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"content": text}
        reply_to = self._progress_reply_to.get(chat_id)
        if reply_to:
            payload["message_reference"] = {"message_id": reply_to}
            payload["allowed_mentions"] = {"replied_user": False}
        return payload

    async def _update_progress_text(
        self,
        chat_id: str,
        handle: str | None,
        text: str,
    ) -> str | None:
        if not handle:
            return None
        url = f"{DISCORD_API_BASE}/channels/{chat_id}/messages/{handle}"
        response = await self._send_payload(url, {"content": text}, method="PATCH")
        return str(response.get("id", handle)) if response else handle

    async def _send_payload(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        method: str = "POST",
    ) -> dict[str, Any] | None:
        if not self._http:
            return None
        token = self.config.token.get_secret_value()
        headers = {"Authorization": f"Bot {token}"}
        for attempt in range(3):
            try:
                response = await self._http.request(method, url, headers=headers, json=payload)
                if response.status_code == 429:
                    data = response.json()
                    retry_after = float(data.get("retry_after", 1.0))
                    logger.warning("⚠️ 限流重试 / rate limited: {}s", retry_after)
                    await asyncio.sleep(retry_after)
                    continue
                response.raise_for_status()
                data = response.json()
                return data if isinstance(data, dict) else {}
            except Exception as exc:
                if attempt == 2:
                    logger.error("❌ 发送失败 / send failed: {}", exc)
                else:
                    await asyncio.sleep(1)
        return None

    async def _send_file(self, chat_id: str, file_path: str, reply_to: str | None = None) -> bool:
        if not self._http:
            return False

        path = Path(file_path)
        if not path.is_file():
            logger.warning("⚠️ 文件缺失 / file missing: {}", file_path)
            return False
        if path.stat().st_size > MAX_ATTACHMENT_BYTES:
            logger.warning("⚠️ 附件过大 / attachment too large: {}", path.name)
            return False

        token = self.config.token.get_secret_value()
        headers = {"Authorization": f"Bot {token}"}
        url = f"{DISCORD_API_BASE}/channels/{chat_id}/messages"
        payload_json: dict[str, Any] = {}
        if reply_to:
            payload_json["message_reference"] = {"message_id": reply_to}
            payload_json["allowed_mentions"] = {"replied_user": False}

        try:
            with open(path, "rb") as file_obj:
                files = {"files[0]": (path.name, file_obj, "application/octet-stream")}
                data: dict[str, Any] = {}
                if payload_json:
                    data["payload_json"] = json.dumps(payload_json)
                response = await self._http.post(url, headers=headers, files=files, data=data)
            if response.status_code == 429:
                logger.warning("⚠️ 限流失败 / attachment rate limited: {}", path.name)
                return False
            response.raise_for_status()
            return True
        except Exception as exc:
            logger.error("❌ 发送失败 / attachment send failed: {}: {}", path.name, exc)
            return False

    async def _start_typing(self, channel_id: str) -> None:
        await self._stop_typing(channel_id)

        async def typing_loop() -> None:
            url = f"{DISCORD_API_BASE}/channels/{channel_id}/typing"
            token = self.config.token.get_secret_value()
            headers = {"Authorization": f"Bot {token}"}
            consecutive_failures = 0
            while self._running:
                try:
                    http = self._http
                    if http is None:
                        break
                    await http.post(url, headers=headers)
                    consecutive_failures = 0
                except Exception:
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        logger.debug(
                            "Discord typing stopped: {} consecutive HTTP failures for channel {}",
                            consecutive_failures,
                            channel_id,
                        )
                        break
                await asyncio.sleep(8)

        self._typing_tasks[channel_id] = asyncio.create_task(typing_loop())

    async def _stop_typing(self, channel_id: str) -> None:
        task = self._typing_tasks.pop(channel_id, None)
        if task:
            task.cancel()
