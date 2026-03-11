"""Base channel interface for chat platforms."""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from bao.bus.events import InboundMessage, OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels.progress_text import ProgressHandler


class BaseChannel(ABC):
    """
    Abstract base class for chat channel implementations.

    Each channel (Telegram, Discord, etc.) should implement this interface
    to integrate with the Bao message bus.
    """

    name: str = "base"

    def __init__(self, config: Any, bus: MessageBus):
        """
        Initialize the channel.

        Args:
            config: Channel-specific configuration.
            bus: The message bus for communication.
        """
        self.config = config
        self.bus = bus
        self._running = False
        self._ready = asyncio.Event()
        self._stop_event: asyncio.Event | None = None
        self._progress_handler: ProgressHandler | None = None

    def _start_lifecycle(self) -> None:
        self._running = True
        self._stop_event = asyncio.Event()

    def _stop_lifecycle(self) -> None:
        self._running = False
        stop_event = self._stop_event
        if stop_event is not None:
            stop_event.set()

    def _reset_lifecycle(self) -> None:
        self._stop_event = None

    async def _wait_until_stopped(self) -> None:
        stop_event = self._stop_event
        if stop_event is None:
            return
        await stop_event.wait()

    async def _wait_stop_or_timeout(self, timeout_s: float) -> bool:
        stop_event = self._stop_event
        if stop_event is None:
            if timeout_s > 0:
                await asyncio.sleep(timeout_s)
            return False
        if timeout_s <= 0:
            return stop_event.is_set()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=timeout_s)
            return True
        except asyncio.TimeoutError:
            return False

    async def _run_reconnect_loop(
        self,
        run_once: Callable[[], Awaitable[None]],
        *,
        label: str,
        delay_s: float = 5.0,
    ) -> None:
        delay_text = int(delay_s) if float(delay_s).is_integer() else delay_s
        while self._running:
            try:
                await run_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                logger.warning("⚠️ {} 连接异常 / connection error: {}", label, e)
            if not self._running:
                break
            logger.info("🔄 {} 准备重连 / reconnecting: wait={}s", label, delay_text)
            if await self._wait_stop_or_timeout(delay_s):
                break

    @abstractmethod
    async def start(self) -> None:
        """
        Start the channel and begin listening for messages.

        This should be a long-running async task that:
        1. Connects to the chat platform
        2. Listens for incoming messages
        3. Forwards messages to the bus via _handle_message()
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel and clean up resources."""
        pass

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """
        Send a message through this channel.

        Args:
            msg: The message to send.
        """
        pass

    def is_allowed(self, sender_id: str) -> bool:
        """
        Check if a sender is allowed to use this bot.

        Args:
            sender_id: The sender's identifier.

        Returns:
            True if allowed, False otherwise.
        """
        allow_list = getattr(self.config, "allow_from", [])

        # If no allow list, allow everyone
        if not allow_list:
            return True

        sender_str = str(sender_id)
        if sender_str in allow_list:
            return True
        if "|" in sender_str:
            for part in sender_str.split("|"):
                if part and part in allow_list:
                    return True
        return False

    async def _handle_message(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Handle an incoming message from the chat platform.

        This method checks permissions and forwards to the bus.

        Args:
            sender_id: The sender's identifier.
            chat_id: The chat/channel identifier.
            content: Message text content.
            media: Optional list of media URLs.
            metadata: Optional channel-specific metadata.
        """
        if not self.is_allowed(sender_id):
            logger.warning(
                "⚠️ 访问拒绝 / access denied: sender={} channel={}",
                sender_id,
                self.name,
            )
            return

        msg = InboundMessage(
            channel=self.name,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=content,
            media=media or [],
            metadata=metadata or {},
        )

        await self.bus.publish_inbound(msg)

    @property
    def is_running(self) -> bool:
        """Check if the channel is running."""
        return self._running

    def mark_ready(self) -> None:
        self._ready.set()

    def mark_not_ready(self) -> None:
        self._ready.clear()

    async def wait_ready(self) -> None:
        await self._ready.wait()

    @property
    def supports_progress(self) -> bool:
        return self._progress_handler is not None

    async def _dispatch_progress_text(self, msg: OutboundMessage, *, flush_progress: bool) -> bool:
        handler = self._progress_handler
        if handler is None:
            return False

        meta = msg.metadata or {}
        await handler.handle(
            msg.chat_id,
            msg.content or "",
            is_progress=bool(meta.get("_progress")),
            is_tool_hint=bool(meta.get("_tool_hint")),
            clear_only=bool(meta.get("_progress_clear")),
        )
        if bool(meta.get("_progress")) and not bool(meta.get("_tool_hint")) and flush_progress:
            await handler.flush(msg.chat_id, force=False)
        return True

    def _clear_progress(self) -> None:
        if self._progress_handler is not None:
            self._progress_handler.clear_all()
