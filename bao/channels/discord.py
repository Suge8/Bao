"""Discord channel implementation using Discord Gateway websocket."""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import websockets
from loguru import logger

from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.channels.progress_text import EditingProgress
from bao.config.schema import DiscordConfig
from bao.utils.helpers import get_media_path

DISCORD_API_BASE = "https://discord.com/api/v10"
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024  # 20MB
MAX_MESSAGE_LEN = 2000  # Discord message character limit


def _split_message(content: str, max_len: int = MAX_MESSAGE_LEN) -> list[str]:
    """Split content into chunks within max_len, preferring line breaks."""
    if not content:
        return []
    if len(content) <= max_len:
        return [content]
    chunks: list[str] = []
    while content:
        if len(content) <= max_len:
            chunks.append(content)
            break
        cut = content[:max_len]
        pos = cut.rfind("\n")
        if pos <= 0:
            pos = cut.rfind(" ")
        if pos <= 0:
            pos = max_len
        chunks.append(content[:pos])
        content = content[pos:].lstrip()
    return chunks


class DiscordChannel(BaseChannel):
    """Discord channel using Gateway websocket."""

    name = "discord"

    def __init__(self, config: DiscordConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: DiscordConfig = config
        self._ws: Any = None
        self._seq: int | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._typing_tasks: dict[str, asyncio.Task[None]] = {}
        self._http: httpx.AsyncClient | None = None
        self._progress_reply_to: dict[str, str | None] = {}
        self._bot_user_id: str | None = None
        self._progress_handler = EditingProgress(
            self._create_progress_text,
            self._update_progress_text,
            self._send_text,
            split_fn=_split_message,
        )
        # RESUME support
        self._session_id: str | None = None
        self._resume_gateway_url: str | None = None
        self._heartbeat_acked: bool = True
        self._should_resume: bool = False

    async def start(self) -> None:
        """Start the Discord gateway connection."""
        if not self.config.token.get_secret_value():
            logger.error("❌ 未配置 / not configured: Discord token")
            return

        self._start_lifecycle()
        self._http = httpx.AsyncClient(timeout=30.0)

        async def _run_once() -> None:
            url = self._resume_gateway_url or self.config.gateway_url
            logger.info("📡 连接网关 / connecting: Discord gateway")
            async with websockets.connect(url) as ws:
                self._ws = ws
                try:
                    await self._gateway_loop()
                finally:
                    self._ws = None

        await self._run_reconnect_loop(_run_once, label="Discord 网关")

    async def stop(self) -> None:
        """Stop the Discord channel."""
        self._clear_progress()
        self._progress_reply_to.clear()
        self._stop_lifecycle()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        for task in self._typing_tasks.values():
            task.cancel()
        self._typing_tasks.clear()
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._http:
            await self._http.aclose()
            self._http = None
        self._reset_lifecycle()

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Discord REST API."""
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

        dispatch_msg = msg
        if (not dispatch_msg.content) and failed_media and not sent_media:
            dispatch_msg = OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="\n".join(f"[attachment: {name} - send failed]" for name in failed_media),
                reply_to=msg.reply_to,
                media=[],
                metadata=dict(msg.metadata),
            )

        self._progress_reply_to[msg.chat_id] = msg.reply_to if not sent_media else None

        try:
            await self._dispatch_progress_text(dispatch_msg, flush_progress=True)
            meta = dispatch_msg.metadata or {}
            if bool(meta.get("_progress_clear")) or not bool(meta.get("_progress")):
                self._progress_reply_to.pop(msg.chat_id, None)
        finally:
            await self._stop_typing(msg.chat_id)

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
        self, chat_id: str, handle: str | None, text: str
    ) -> str | None:
        if not handle:
            return None
        url = f"{DISCORD_API_BASE}/channels/{chat_id}/messages/{handle}"
        response = await self._send_payload(url, {"content": text}, method="PATCH")
        return str(response.get("id", handle)) if response else handle

    async def _send_payload(
        self, url: str, payload: dict[str, Any], *, method: str = "POST"
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
            except Exception as e:
                if attempt == 2:
                    logger.error("❌ 发送失败 / send failed: {}", e)
                else:
                    await asyncio.sleep(1)
        return None

    async def _gateway_loop(self) -> None:
        """Main gateway loop: identify/resume, heartbeat, dispatch events."""
        if not self._ws:
            return

        async for raw in self._ws:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.debug("Invalid JSON from Discord gateway: {}", raw[:100])
                continue

            op = data.get("op")
            event_type = data.get("t")
            seq = data.get("s")
            payload = data.get("d")

            if seq is not None:
                self._seq = seq

            if op == 10:
                # HELLO: start heartbeat, then identify or resume
                interval_ms = payload.get("heartbeat_interval", 45000)
                await self._start_heartbeat(interval_ms / 1000)
                if self._should_resume and self._session_id:
                    await self._resume()
                else:
                    await self._identify()
            elif op == 11:
                # HEARTBEAT_ACK: connection is alive
                self._heartbeat_acked = True
            elif op == 0 and event_type == "READY":
                # Store session info for future RESUME
                self._session_id = payload.get("session_id")
                self._resume_gateway_url = payload.get("resume_gateway_url")
                user = payload.get("user") or {}
                self._bot_user_id = str(user.get("id")) if user.get("id") else None
                self._should_resume = True
                logger.debug("Discord gateway READY (session={})", self._session_id)
            elif op == 0 and event_type == "RESUMED":
                logger.debug("Discord gateway RESUMED successfully")
            elif op == 0 and event_type == "MESSAGE_CREATE":
                await self._handle_message_create(payload)
            elif op == 7:
                # RECONNECT: server requests reconnect, try RESUME
                logger.info("🔄 收到重连 / reconnect requested: Discord gateway")
                self._should_resume = True
                break
            elif op == 9:
                # INVALID_SESSION: d=true means resumable, d=false means fresh identify
                resumable = payload is True
                logger.warning("⚠️ 会话失效 / invalid session: resumable={}", resumable)
                self._should_resume = resumable
                if not resumable:
                    self._session_id = None
                    self._resume_gateway_url = None
                await asyncio.sleep(1 + 4 * (not resumable))  # 1s if resumable, 5s if not
                break

    async def _identify(self) -> None:
        """Send IDENTIFY payload."""
        if not self._ws:
            return

        identify = {
            "op": 2,
            "d": {
                "token": self.config.token.get_secret_value(),
                "intents": self.config.intents,
                "properties": {
                    "os": "Bao",
                    "browser": "Bao",
                    "device": "Bao",
                },
            },
        }
        await self._ws.send(json.dumps(identify, ensure_ascii=False))

    async def _resume(self) -> None:
        """Send RESUME payload to replay missed events."""
        if not self._ws:
            return
        resume = {
            "op": 6,
            "d": {
                "token": self.config.token.get_secret_value(),
                "session_id": self._session_id,
                "seq": self._seq,
            },
        }
        logger.debug("Discord sending RESUME (seq={})", self._seq)
        await self._ws.send(json.dumps(resume, ensure_ascii=False))

    async def _start_heartbeat(self, interval_s: float) -> None:
        """Start or restart the heartbeat loop with ACK-based zombie detection."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._heartbeat_acked = True

        async def heartbeat_loop() -> None:
            while self._running and self._ws:
                if not self._heartbeat_acked:
                    logger.debug(
                        "Discord heartbeat ACK not received — zombie connection, reconnecting"
                    )
                    await self._ws.close()
                    break
                self._heartbeat_acked = False
                try:
                    await self._ws.send(json.dumps({"op": 1, "d": self._seq}, ensure_ascii=False))
                except Exception as e:
                    logger.debug("Discord heartbeat failed: {}", e)
                    break
                await asyncio.sleep(interval_s)

        self._heartbeat_task = asyncio.create_task(heartbeat_loop())

    async def _handle_message_create(self, payload: dict[str, Any]) -> None:
        """Handle incoming Discord messages."""
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

        content_parts = [content] if content else []
        media_paths: list[str] = []
        media_dir = get_media_path()

        for attachment in payload.get("attachments") or []:
            url = attachment.get("url")
            filename = attachment.get("filename") or "attachment"
            size = attachment.get("size") or 0
            if not url or not self._http:
                continue
            if size and size > MAX_ATTACHMENT_BYTES:
                content_parts.append(f"[attachment: {filename} - too large]")
                continue
            try:
                media_dir.mkdir(parents=True, exist_ok=True)
                file_path = (
                    media_dir / f"{attachment.get('id', 'file')}_{filename.replace('/', '_')}"
                )
                resp = await self._http.get(url)
                resp.raise_for_status()
                file_path.write_bytes(resp.content)
                media_paths.append(str(file_path))
                content_parts.append(f"[attachment: {file_path}]")
            except Exception as e:
                logger.warning("⚠️ 下载失败 / attachment failed: {}", e)
                content_parts.append(f"[attachment: {filename} - download failed]")

        reply_to = str(payload.get("id") or "")
        referenced_message_id = (payload.get("referenced_message") or {}).get("id")

        await self._start_typing(channel_id)

        await self._handle_message(
            sender_id=sender_id,
            chat_id=channel_id,
            content="\n".join(p for p in content_parts if p) or "[empty message]",
            media=media_paths,
            metadata={
                "message_id": str(payload.get("id", "")),
                "guild_id": guild_id,
                "reply_to": reply_to or None,
                "referenced_message_id": str(referenced_message_id)
                if referenced_message_id
                else None,
            },
        )

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
            with open(path, "rb") as f:
                files = {"files[0]": (path.name, f, "application/octet-stream")}
                data: dict[str, Any] = {}
                if payload_json:
                    data["payload_json"] = json.dumps(payload_json)
                response = await self._http.post(url, headers=headers, files=files, data=data)
            if response.status_code == 429:
                logger.warning("⚠️ 限流失败 / attachment rate limited: {}", path.name)
                return False
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error("❌ 发送失败 / attachment send failed: {}: {}", path.name, e)
        return False

    async def _start_typing(self, channel_id: str) -> None:
        """Start periodic typing indicator for a channel."""
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
        """Stop typing indicator for a channel."""
        task = self._typing_tasks.pop(channel_id, None)
        if task:
            task.cancel()
