"""WhatsApp channel implementation using Node.js bridge."""

import base64
import json
import mimetypes
from collections import OrderedDict
from typing import Any, Protocol

from loguru import logger

from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.channels.progress_text import ProgressBuffer
from bao.config.schema import WhatsAppConfig
from bao.utils.helpers import get_media_path


class _BridgeWebSocket(Protocol):
    async def send(self, message: Any, /, text: bool | None = None) -> Any: ...

    async def close(self) -> Any: ...


class WhatsAppChannel(BaseChannel):
    """
    WhatsApp channel that connects to a Node.js bridge.

    The bridge uses @whiskeysockets/baileys to handle the WhatsApp Web protocol.
    Communication between Python and Node.js is via WebSocket.
    """

    name = "whatsapp"

    def __init__(self, config: WhatsAppConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: WhatsAppConfig = config
        self._ws: _BridgeWebSocket | None = None
        self._connected = False
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()
        self._progress_handler = ProgressBuffer(self._send_text)

    async def start(self) -> None:
        """Start the WhatsApp channel by connecting to the bridge."""
        self.mark_not_ready()
        import websockets

        bridge_url = self.config.bridge_url

        logger.info("📡 连接桥接 / connecting: {}", bridge_url)

        self._start_lifecycle()

        async def _run_once() -> None:
            async with websockets.connect(bridge_url) as ws:
                self._ws = ws
                try:
                    bridge_token = self.config.bridge_token.get_secret_value()
                    if bridge_token:
                        await ws.send(
                            json.dumps(
                                {"type": "auth", "token": bridge_token},
                                ensure_ascii=False,
                            )
                        )
                    self._connected = True
                    logger.info("✅ 连接成功 / connected: WhatsApp bridge")
                    self.mark_ready()

                    async for message in ws:
                        try:
                            await self._handle_bridge_message(message)
                        except Exception as e:
                            logger.error("❌ 处理失败 / message error: {}", e)
                finally:
                    self._connected = False
                    self._ws = None
                    self.mark_not_ready()

        await self._run_reconnect_loop(_run_once, label="WhatsApp bridge")

    async def stop(self) -> None:
        """Stop the WhatsApp channel."""
        self._clear_progress()
        self._stop_lifecycle()
        self._connected = False
        self.mark_not_ready()
        ws = self._ws
        if ws is not None:
            await ws.close()
            self._ws = None
        self._reset_lifecycle()

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through WhatsApp."""
        await self._dispatch_progress_text(msg, flush_progress=False)

    async def _send_text(self, chat_id: str, text: str) -> None:
        """Send raw text via WebSocket bridge."""
        ws = self._ws
        if ws is None or not self._connected:
            logger.warning("⚠️ 未连接 / not connected: WhatsApp bridge")
            return
        try:
            payload = {"type": "send", "to": chat_id, "text": text}
            await ws.send(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            logger.error("❌ 发送失败 / send failed: {}", e)

    def _save_media(self, media: dict[str, Any], sender_id: str) -> list[str]:
        """Decode base64 media from bridge and save to disk."""
        try:
            raw = base64.b64decode(media["data"])
            mimetype = media.get("mimetype", "application/octet-stream")
            filename = media.get("filename")
            if not filename:
                ext = mimetypes.guess_extension(mimetype) or ""
                filename = f"wa_{sender_id}_{id(raw):x}{ext}"
            media_dir = get_media_path()
            path = media_dir / filename.replace("/", "_")
            path.write_bytes(raw)
            logger.debug("Saved WhatsApp media: {}", path)
            return [str(path)]
        except Exception as e:
            logger.warning("⚠️ 保存失败 / save failed: {}", e)
            return []

    async def _handle_bridge_message(self, raw: str | bytes) -> None:
        """Handle a message from the bridge."""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("Invalid JSON from bridge: {}", raw[:100])
            return

        msg_type = data.get("type")

        if msg_type == "message":
            message_id = str(data.get("id") or "").strip()
            if message_id:
                if message_id in self._processed_message_ids:
                    logger.debug("Duplicate WhatsApp message skipped: {}", message_id)
                    return
                self._processed_message_ids[message_id] = None
                while len(self._processed_message_ids) > 1000:
                    self._processed_message_ids.popitem(last=False)

            pn = data.get("pn", "")
            sender = data.get("sender", "")
            participant = data.get("participant", "")
            content = data.get("content", "")
            is_group = bool(data.get("isGroup", False))

            if is_group and participant:
                user_id = participant
            else:
                user_id = pn if pn else sender
            sender_id = user_id.split("@")[0] if "@" in user_id else user_id
            logger.debug("Sender {}", sender)

            if not self.is_allowed(sender_id):
                logger.warning(
                    "⚠️ 访问拒绝 / access denied: sender={} channel=whatsapp",
                    sender_id,
                )
                return

            # Save media from bridge if present
            media_paths: list[str] = []
            media_data = data.get("media")
            if media_data and isinstance(media_data, dict):
                media_paths = self._save_media(media_data, sender_id)

            # Voice message placeholder
            if content == "[Voice Message]" and not media_paths:
                content = "[Voice Message: Transcription not available for WhatsApp yet]"

            await self._handle_message(
                sender_id=sender_id,
                chat_id=sender,
                content=content,
                media=media_paths,
                metadata={
                    "message_id": message_id or data.get("id"),
                    "timestamp": data.get("timestamp"),
                    "is_group": is_group,
                    "participant": participant,
                },
            )

        elif msg_type == "status":
            # Connection status update
            status = data.get("status")
            logger.info("📡 状态更新 / status update: {}", status)

            if status == "connected":
                self._connected = True
            elif status == "disconnected":
                self._connected = False

        elif msg_type == "qr":
            # QR code for authentication
            logger.info("📱 扫码连接 / scan qr: bridge terminal")

        elif msg_type == "error":
            logger.error("❌ 服务异常 / bridge error: {}", data.get("error"))
