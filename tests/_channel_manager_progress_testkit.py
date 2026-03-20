# ruff: noqa: F401
from __future__ import annotations

import asyncio
import json
from contextlib import suppress

import pytest

from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.channels.manager import ChannelManager
from bao.config.schema import Config, IMessageConfig


class _DummyChannel(BaseChannel):
    name = "dummy"

    def __init__(self, bus: MessageBus):
        super().__init__(IMessageConfig(enabled=True), bus)
        self.sent: list[OutboundMessage] = []

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        self.sent.append(msg)


class _DummyProgressHandler:
    async def handle(self, *_args, **_kwargs) -> None:
        return None

    async def flush(self, *_args, **_kwargs) -> None:
        return None

    def clear_all(self) -> None:
        return None


class _FailingStartChannel(_DummyChannel):
    async def start(self) -> None:
        raise RuntimeError("boom-start")


class _FailingSendChannel(_DummyChannel):
    async def send(self, msg: OutboundMessage) -> None:
        _ = msg
        raise RuntimeError("boom-send")


def _dispatch_one(
    manager: ChannelManager, bus: MessageBus, msg: OutboundMessage, channel: _DummyChannel
) -> None:
    async def _run() -> None:
        task = asyncio.create_task(manager._dispatch_outbound())
        try:
            await bus.publish_outbound(msg)
            for _ in range(20):
                if channel.sent:
                    break
                await asyncio.sleep(0.01)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    asyncio.run(_run())


__all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]
