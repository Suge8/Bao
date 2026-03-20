"""Channel manager for coordinating chat channels."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from loguru import logger

from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels._manager_coding_meta import transform_coding_meta
from bao.channels._manager_registry import ChannelRegistryContext, init_channels
from bao.channels.base import BaseChannel
from bao.config.schema import Config
from bao.delivery import DeliveryResult


class ChannelManager:
    """
    Manages chat channels and coordinates message routing.

    Responsibilities:
    - Initialize enabled channels (Telegram, WhatsApp, etc.)
    - Start/stop channels
    - Route outbound messages
    """

    def __init__(
        self,
        config: Config,
        bus: MessageBus,
        on_channel_error: Callable[[str, str, str], None] | None = None,
    ):
        self.config = config
        self.bus = bus
        self.channels: dict[str, BaseChannel] = {}
        self._dispatch_task: asyncio.Task[None] | None = None
        self._started = asyncio.Event()
        self._on_channel_error = on_channel_error

        self._init_channels()

    def _report_channel_error(self, stage: str, name: str, detail: Any) -> None:
        callback = self._on_channel_error
        if callback is None:
            return
        try:
            callback(stage, name, str(detail))
        except Exception as exc:
            logger.debug("Skip channel error callback {} {}: {}", stage, name, exc)

    def _report_unavailable(self, name: str, detail: Any) -> None:
        logger.warning("⚠️ 通道不可用 / unavailable: {} {}", name, detail)
        self._report_channel_error("unavailable", name.lower(), detail)

    def _init_channels(self) -> None:
        init_channels(
            ChannelRegistryContext(
                config=self.config,
                bus=self.bus,
                channels=self.channels,
                report_unavailable=self._report_unavailable,
            )
        )

    async def _start_channel(self, name: str, channel: BaseChannel) -> None:
        """Start a channel and log any exceptions."""
        try:
            await channel.start()
        except Exception as e:
            logger.error("❌ 启动失败 / start failed: {}: {}", name, e)
            self._report_channel_error("start_failed", name, e)

    async def start_all(self) -> None:
        """Start all channels and the outbound dispatcher."""
        if not self.channels:
            logger.warning("⚠️ 通道为空 / no channels: enabled=0")
            self._started.set()
            return

        # Start outbound dispatcher
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())

        # Start channels
        tasks = []
        for name, channel in self.channels.items():
            logger.info("📡 启动通道 / starting: {}", name)
            tasks.append(asyncio.create_task(self._start_channel(name, channel)))

        self._started.set()

        # Wait for all to complete (they should run forever)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def wait_started(self) -> None:
        await self._started.wait()

    async def wait_ready(self, name: str) -> None:
        channel = self.channels.get(name)
        if not channel:
            return
        await channel.wait_ready()

    async def send_outbound(self, msg: OutboundMessage) -> None:
        await self._deliver_outbound(msg, strict=False)

    async def deliver_outbound(self, msg: OutboundMessage) -> DeliveryResult:
        result = await self._deliver_outbound(msg, strict=True)
        assert result is not None
        return result

    async def _deliver_outbound(
        self,
        msg: OutboundMessage,
        *,
        strict: bool,
    ) -> DeliveryResult | None:
        channel = self.channels.get(msg.channel)
        if not channel:
            if strict:
                raise RuntimeError(f"unknown channel: {msg.channel}")
            if msg.channel != "desktop":
                logger.warning("⚠️ 未知通道 / unknown channel: {}", msg.channel)
            return None
        if strict and (not channel.is_running or not channel.is_ready):
            raise RuntimeError(f"channel not ready: {msg.channel}")
        if msg.metadata.get("_progress"):
            defaults = self.config.agents.defaults
            if not channel.supports_progress:
                if strict:
                    raise RuntimeError(f"channel does not support progress: {msg.channel}")
                return None
            is_tool_hint = msg.metadata.get("_tool_hint", False)
            allow_tool_hints = defaults.send_tool_hints
            allow_progress = defaults.send_progress
            if is_tool_hint and not allow_tool_hints:
                if not allow_progress:
                    if strict:
                        raise RuntimeError(f"tool hints disabled for channel: {msg.channel}")
                    return None
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
                if strict:
                    raise RuntimeError(f"progress disabled for channel: {msg.channel}")
                return None
        msg = self._transform_coding_meta(msg)
        await channel.send(msg)
        return DeliveryResult.delivered_result(channel=msg.channel, chat_id=msg.chat_id)

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
                self._report_channel_error("stop_failed", name, e)

    async def _dispatch_outbound(self) -> None:
        """Dispatch outbound messages to the appropriate channel.
        Progress and tool-hint messages are gated by config so that
        internal traces never leak to external chat channels.
        """
        logger.debug("Outbound dispatcher started")
        while True:
            try:
                msg = await self.bus.consume_outbound()
                try:
                    await self.send_outbound(msg)
                except Exception as e:
                    logger.error("❌ 发送失败 / send failed: {}: {}", msg.channel, e)
                    self._report_channel_error("send_failed", msg.channel, e)
            except asyncio.CancelledError:
                break

    def get_channel(self, name: str) -> BaseChannel | None:
        """Get a channel by name."""
        return self.channels.get(name)

    def _transform_coding_meta(self, msg: OutboundMessage) -> OutboundMessage:
        return transform_coding_meta(msg)

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
