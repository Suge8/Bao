"""Channel manager for coordinating chat channels."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from loguru import logger

from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.config.schema import Config


class ChannelManager:
    """
    Manages chat channels and coordinates message routing.

    Responsibilities:
    - Initialize enabled channels (Telegram, WhatsApp, etc.)
    - Start/stop channels
    - Route outbound messages
    """

    def __init__(self, config: Config, bus: MessageBus):
        self.config = config
        self.bus = bus
        self.channels: dict[str, BaseChannel] = {}
        self._dispatch_task: asyncio.Task[None] | None = None

        self._init_channels()

    def _init_channels(self) -> None:
        """Initialize channels based on config."""

        # Telegram channel
        if self.config.channels.telegram.enabled:
            try:
                from bao.channels.telegram import TelegramChannel

                groq_cfg = self.config.providers.get("groq")
                self.channels["telegram"] = TelegramChannel(
                    self.config.channels.telegram,
                    self.bus,
                    groq_api_key=groq_cfg.api_key.get_secret_value() if groq_cfg else "",
                )
                logger.debug("Telegram channel enabled")
            except ImportError as e:
                logger.warning("⚠️ 通道不可用 / unavailable: Telegram {}", e)

        # WhatsApp channel
        if self.config.channels.whatsapp.enabled:
            try:
                from bao.channels.whatsapp import WhatsAppChannel

                self.channels["whatsapp"] = WhatsAppChannel(self.config.channels.whatsapp, self.bus)
                logger.debug("WhatsApp channel enabled")
            except ImportError as e:
                logger.warning("⚠️ 通道不可用 / unavailable: WhatsApp {}", e)

        # Discord channel
        if self.config.channels.discord.enabled:
            try:
                from bao.channels.discord import DiscordChannel

                self.channels["discord"] = DiscordChannel(self.config.channels.discord, self.bus)
                logger.debug("Discord channel enabled")
            except ImportError as e:
                logger.warning("⚠️ 通道不可用 / unavailable: Discord {}", e)

        # Feishu channel
        if self.config.channels.feishu.enabled:
            try:
                from bao.channels.feishu import FEISHU_AVAILABLE, FeishuChannel

                if FEISHU_AVAILABLE:
                    self.channels["feishu"] = FeishuChannel(self.config.channels.feishu, self.bus)
                    logger.debug("Feishu channel enabled")
                else:
                    logger.warning("⚠️ 通道不可用 / unavailable: Feishu sdk missing")
            except ImportError as e:
                logger.warning("⚠️ 通道不可用 / unavailable: Feishu {}", e)

        # Mochat channel
        if self.config.channels.mochat.enabled:
            try:
                from bao.channels.mochat import MochatChannel

                self.channels["mochat"] = MochatChannel(self.config.channels.mochat, self.bus)
                logger.debug("Mochat channel enabled")
            except ImportError as e:
                logger.warning("⚠️ 通道不可用 / unavailable: Mochat {}", e)

        # DingTalk channel
        if self.config.channels.dingtalk.enabled:
            try:
                from bao.channels.dingtalk import DINGTALK_AVAILABLE, DingTalkChannel

                if DINGTALK_AVAILABLE:
                    self.channels["dingtalk"] = DingTalkChannel(
                        self.config.channels.dingtalk, self.bus
                    )
                    logger.debug("DingTalk channel enabled")
                else:
                    logger.warning("⚠️ 通道不可用 / unavailable: DingTalk sdk missing")
            except ImportError as e:
                logger.warning("⚠️ 通道不可用 / unavailable: DingTalk {}", e)

        # Email channel
        if self.config.channels.email.enabled:
            try:
                from bao.channels.email import EmailChannel

                self.channels["email"] = EmailChannel(self.config.channels.email, self.bus)
                logger.debug("Email channel enabled")
            except ImportError as e:
                logger.warning("⚠️ 通道不可用 / unavailable: Email {}", e)

        # Slack channel
        if self.config.channels.slack.enabled:
            try:
                from bao.channels.slack import SlackChannel

                self.channels["slack"] = SlackChannel(self.config.channels.slack, self.bus)
                logger.debug("Slack channel enabled")
            except ImportError as e:
                logger.warning("⚠️ 通道不可用 / unavailable: Slack {}", e)

        # QQ channel
        if self.config.channels.qq.enabled:
            try:
                from bao.channels.qq import QQ_AVAILABLE, QQChannel

                if QQ_AVAILABLE:
                    self.channels["qq"] = QQChannel(
                        self.config.channels.qq,
                        self.bus,
                    )
                    logger.debug("QQ channel enabled")
                else:
                    logger.warning("⚠️ 通道不可用 / unavailable: QQ sdk missing")
            except ImportError as e:
                logger.warning("⚠️ 通道不可用 / unavailable: QQ {}", e)

        # iMessage channel (macOS only)
        if self.config.channels.imessage.enabled:
            try:
                from bao.channels.imessage import IMessageChannel

                self.channels["imessage"] = IMessageChannel(self.config.channels.imessage, self.bus)
                logger.debug("iMessage channel enabled")
            except ImportError as e:
                logger.warning("⚠️ 通道不可用 / unavailable: iMessage {}", e)

    async def _start_channel(self, name: str, channel: BaseChannel) -> None:
        """Start a channel and log any exceptions."""
        try:
            await channel.start()
        except Exception as e:
            logger.error("❌ 启动失败 / start failed: {}: {}", name, e)

    async def start_all(self) -> None:
        """Start all channels and the outbound dispatcher."""
        if not self.channels:
            logger.warning("⚠️ 通道为空 / no channels: enabled=0")
            return

        # Start outbound dispatcher
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())

        # Start channels
        tasks = []
        for name, channel in self.channels.items():
            logger.info("📡 启动通道 / starting: {}", name)
            tasks.append(asyncio.create_task(self._start_channel(name, channel)))

        # Wait for all to complete (they should run forever)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_all(self) -> None:
        """Stop all channels and the dispatcher."""
        logger.info("📡 停止通道 / stopping: all channels")

        # Stop dispatcher
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass

        # Stop all channels
        for name, channel in self.channels.items():
            try:
                await channel.stop()
                logger.info("✅ 已停止 / stopped: {}", name)
            except Exception as e:
                logger.error("❌ 停止失败 / stop failed: {}: {}", name, e)

    async def _dispatch_outbound(self) -> None:
        """Dispatch outbound messages to the appropriate channel.
        Progress and tool-hint messages are gated by config so that
        internal traces never leak to external chat channels.
        """
        logger.debug("Outbound dispatcher started")
        defaults = self.config.agents.defaults
        while True:
            try:
                msg = await asyncio.wait_for(self.bus.consume_outbound(), timeout=1.0)
                channel = self.channels.get(msg.channel)
                if not channel:
                    if msg.channel != "desktop":
                        logger.warning("⚠️ 未知通道 / unknown channel: {}", msg.channel)
                    continue
                if msg.metadata.get("_progress"):
                    is_tool_hint = msg.metadata.get("_tool_hint", False)
                    allow_tool_hints = defaults.send_tool_hints
                    allow_progress = defaults.send_progress
                    if is_tool_hint and not allow_tool_hints:
                        if not allow_progress:
                            continue
                        if not hasattr(channel, "_progress"):
                            continue
                        suppressed_meta = dict(msg.metadata)
                        suppressed_meta["_tool_hint_suppressed"] = True
                        msg = OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content="",
                            reply_to=msg.reply_to,
                            media=msg.media,
                            metadata=suppressed_meta,
                        )
                    if not is_tool_hint and not allow_progress:
                        continue
                msg = self._transform_coding_meta(msg)
                try:
                    await channel.send(msg)
                except Exception as e:
                    logger.error("❌ 发送失败 / send failed: {}: {}", msg.channel, e)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    def get_channel(self, name: str) -> BaseChannel | None:
        """Get a channel by name."""
        return self.channels.get(name)

    @staticmethod
    def _parse_meta_line(content: str, marker: str) -> tuple[dict[str, Any] | None, str]:
        if marker not in content:
            return None, content
        lines = content.splitlines()
        meta: dict[str, Any] | None = None
        kept: list[str] = []
        for line in lines:
            if line.startswith(marker) and meta is None:
                raw = line.split("=", 1)[1].strip()
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        meta = parsed
                        continue
                except Exception:
                    pass
            kept.append(line)
        cleaned = "\n".join(kept).rstrip("\n")
        return meta, cleaned

    @staticmethod
    def _render_coding_status(provider: str, meta: dict[str, Any]) -> str:
        status = str(meta.get("status") or "unknown")
        icon = {"success": "✅", "error": "❌", "timeout": "⏱️"}.get(status, "⌨️")
        attempts = meta.get("attempts")
        duration_ms = meta.get("duration_ms")
        session_id = meta.get("session_id")
        error_type = meta.get("error_type")

        parts = [f"{icon} {provider} status: {status}"]
        if isinstance(attempts, int):
            parts.append(f"attempts={attempts}")
        if isinstance(duration_ms, int):
            parts.append(f"duration={duration_ms / 1000:.1f}s")
        if isinstance(session_id, str) and session_id:
            parts.append(f"session={session_id}")
        if isinstance(error_type, str) and error_type:
            parts.append(f"error={error_type}")
        return " | ".join(parts)

    def _transform_coding_meta(self, msg: OutboundMessage) -> OutboundMessage:
        if msg.metadata.get("_progress"):
            return msg
        if not msg.content:
            return msg
        for provider, marker, meta_key, status_key in (
            ("OpenCode", "OPENCODE_META=", "_opencode_meta", "_opencode_status"),
            ("Codex", "CODEX_META=", "_codex_meta", "_codex_status"),
            ("Claude Code", "CLAUDECODE_META=", "_claudecode_meta", "_claudecode_status"),
        ):
            meta, cleaned = self._parse_meta_line(msg.content, marker)
            if not meta:
                continue
            lines = cleaned.splitlines()
            if lines and lines[0].strip().lower() == f"{provider} completed successfully.".lower():
                cleaned = "\n".join(lines[1:]).lstrip("\n")
            status_line = self._render_coding_status(provider, meta)
            final_content = status_line if not cleaned else f"{status_line}\n\n{cleaned}"
            new_meta = dict(msg.metadata)
            new_meta[meta_key] = meta
            new_meta[status_key] = str(meta.get("status") or "unknown")
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=final_content,
                reply_to=msg.reply_to,
                media=msg.media,
                metadata=new_meta,
            )

        return msg

    def get_status(self) -> dict[str, Any]:
        """Get status of all channels."""
        return {
            name: {"enabled": True, "running": channel.is_running}
            for name, channel in self.channels.items()
        }

    @property
    def enabled_channels(self) -> list[str]:
        """Get list of enabled channel names."""
        return list(self.channels.keys())
