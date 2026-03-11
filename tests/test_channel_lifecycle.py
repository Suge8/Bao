from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import websockets
from pydantic import SecretStr

from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.channels.discord import DiscordChannel
from bao.channels.mochat import MochatChannel
from bao.channels.whatsapp import WhatsAppChannel
from bao.config.schema import DiscordConfig, IMessageConfig, MochatConfig, WhatsAppConfig


class _DummyChannel(BaseChannel):
    name = "dummy"

    def __init__(self) -> None:
        super().__init__(IMessageConfig(enabled=True), MessageBus())

    async def start(self) -> None:
        self._start_lifecycle()

    async def stop(self) -> None:
        self._stop_lifecycle()

    async def send(self, msg: OutboundMessage) -> None:
        _ = msg


class _FakeAsyncWs:
    def __init__(self) -> None:
        self.closed = asyncio.Event()
        self.sent: list[str] = []

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    async def close(self) -> None:
        self.closed.set()

    def __aiter__(self) -> _FakeAsyncWs:
        return self

    async def __anext__(self) -> str:
        await self.closed.wait()
        raise StopAsyncIteration


class _AsyncWsContext:
    def __init__(self, ws: _FakeAsyncWs) -> None:
        self._ws = ws

    async def __aenter__(self) -> _FakeAsyncWs:
        return self._ws

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


@pytest.mark.asyncio
async def test_base_reconnect_loop_retries_after_failure() -> None:
    channel = _DummyChannel()
    channel._start_lifecycle()
    attempts = 0

    async def _run_once() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("boom")
        channel._stop_lifecycle()

    await channel._run_reconnect_loop(_run_once, label="dummy", delay_s=0.01)

    assert attempts == 2


@pytest.mark.asyncio
async def test_base_reconnect_loop_delay_wakes_on_stop() -> None:
    channel = _DummyChannel()
    channel._start_lifecycle()
    calls = 0

    async def _run_once() -> None:
        nonlocal calls
        calls += 1

    task = asyncio.create_task(channel._run_reconnect_loop(_run_once, label="dummy", delay_s=60))
    await asyncio.sleep(0)
    channel._stop_lifecycle()
    await asyncio.wait_for(task, timeout=0.5)

    assert calls == 1


@pytest.mark.asyncio
async def test_base_stop_lifecycle_is_idempotent() -> None:
    channel = _DummyChannel()
    channel._start_lifecycle()

    channel._stop_lifecycle()
    channel._stop_lifecycle()

    assert channel._running is False
    assert channel._stop_event is not None and channel._stop_event.is_set()


@pytest.mark.asyncio
async def test_discord_start_waits_until_stop(monkeypatch) -> None:
    channel = DiscordChannel(DiscordConfig(enabled=True, token=SecretStr("x")), MagicMock())
    ws = _FakeAsyncWs()

    monkeypatch.setattr(
        "bao.channels.discord.websockets.connect",
        lambda _url: _AsyncWsContext(ws),
    )

    async def _gateway_loop() -> None:
        await ws.closed.wait()

    channel._gateway_loop = _gateway_loop

    start_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.05)
    assert not start_task.done()

    await channel.stop()
    await asyncio.wait_for(start_task, timeout=0.5)


@pytest.mark.asyncio
async def test_whatsapp_start_waits_until_stop(monkeypatch) -> None:
    channel = WhatsAppChannel(
        WhatsAppConfig(
            enabled=True, bridge_url="ws://localhost:3001", bridge_token=SecretStr("tok")
        ),
        MagicMock(),
    )
    ws = _FakeAsyncWs()

    monkeypatch.setattr(websockets, "connect", lambda _url: _AsyncWsContext(ws))

    start_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.05)
    assert not start_task.done()

    await channel.stop()
    await asyncio.wait_for(start_task, timeout=0.5)
    assert ws.sent


@pytest.mark.asyncio
async def test_mochat_start_waits_until_stop() -> None:
    channel = MochatChannel(
        MochatConfig(enabled=True, claw_token=SecretStr("tok")),
        MagicMock(),
    )
    channel._load_session_cursors = AsyncMock()
    channel._refresh_targets = AsyncMock()
    channel._ensure_fallback_workers = AsyncMock()
    channel._start_socket_client = AsyncMock(return_value=False)

    start_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.05)
    assert not start_task.done()

    await channel.stop()
    await asyncio.wait_for(start_task, timeout=0.5)
