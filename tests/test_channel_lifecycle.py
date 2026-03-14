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
from bao.channels.email import EmailChannel
from bao.channels.imessage import IMessageChannel
from bao.channels.mochat import MochatChannel
from bao.channels.whatsapp import WhatsAppChannel
from bao.config.schema import (
    DiscordConfig,
    EmailConfig,
    IMessageConfig,
    MochatConfig,
    WhatsAppConfig,
)


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


def _email_config() -> EmailConfig:
    return EmailConfig(
        enabled=True,
        consent_granted=True,
        imap_host="imap.example.com",
        imap_port=993,
        imap_username="bot@example.com",
        imap_password="secret",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="bot@example.com",
        smtp_password="secret",
    )


def _new_mochat_channel() -> MochatChannel:
    return MochatChannel(
        MochatConfig(enabled=True, claw_token=SecretStr("tok")),
        MagicMock(),
    )


def _install_waiting_mochat_workers(channel: MochatChannel, gate: asyncio.Event) -> None:
    async def _wait_for_gate(_target_id: str) -> None:
        await gate.wait()

    channel._session_watch_worker = _wait_for_gate  # type: ignore[method-assign]
    channel._panel_poll_worker = _wait_for_gate  # type: ignore[method-assign]


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
    channel = _new_mochat_channel()
    channel._load_session_cursors = AsyncMock()
    channel._refresh_targets = AsyncMock()
    channel._start_socket_client = AsyncMock(return_value=False)
    channel._reconcile_transport_mode = AsyncMock()

    start_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.05)
    assert not start_task.done()

    await channel.stop()
    await asyncio.wait_for(start_task, timeout=0.5)


@pytest.mark.asyncio
async def test_mochat_transport_mode_reuses_and_clears_fallback_workers() -> None:
    channel = _new_mochat_channel()
    channel._running = True
    channel._session_set = {"s1"}
    channel._panel_set = {"p1"}

    gate = asyncio.Event()
    _install_waiting_mochat_workers(channel, gate)

    await channel._reconcile_transport_mode("fallback")
    session_task = channel._session_fallback_tasks["s1"]
    panel_task = channel._panel_fallback_tasks["p1"]

    await channel._reconcile_transport_mode("fallback")

    assert channel._session_fallback_tasks["s1"] is session_task
    assert channel._panel_fallback_tasks["p1"] is panel_task

    await channel._reconcile_transport_mode("socket")

    assert channel._session_fallback_tasks == {}
    assert channel._panel_fallback_tasks == {}

    gate.set()
    await asyncio.gather(session_task, panel_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_email_start_waits_until_stop(monkeypatch) -> None:
    channel = EmailChannel(_email_config(), MagicMock())
    monkeypatch.setattr(channel, "_validate_config", lambda: True)
    monkeypatch.setattr(channel, "_fetch_new_messages", lambda: [])

    start_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.05)
    assert not start_task.done()

    await channel.stop()
    await asyncio.wait_for(start_task, timeout=0.5)


@pytest.mark.asyncio
async def test_imessage_start_waits_until_stop(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "chat.db"
    db_path.write_text("", encoding="utf-8")
    monkeypatch.setattr("bao.channels.imessage.CHAT_DB", db_path)

    channel = IMessageChannel(IMessageConfig(enabled=True), MagicMock())
    monkeypatch.setattr(channel, "_get_max_rowid", lambda: 1)
    channel._poll = AsyncMock()

    start_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0.05)
    assert not start_task.done()

    await channel.stop()
    await asyncio.wait_for(start_task, timeout=0.5)


@pytest.mark.asyncio
async def test_mochat_reconcile_transport_mode_syncs_workers() -> None:
    channel = _new_mochat_channel()
    channel._running = True
    channel._session_set = {"s1"}
    channel._panel_set = {"p1"}
    session_task = asyncio.create_task(asyncio.sleep(60))
    panel_task = asyncio.create_task(asyncio.sleep(60))
    stale_task = asyncio.create_task(asyncio.sleep(60))
    channel._session_fallback_tasks = {"s1": session_task, "stale": stale_task}
    channel._panel_fallback_tasks = {"p1": panel_task}

    created_sessions: list[str] = []
    created_panels: list[str] = []

    async def _session_watch_worker(session_id: str) -> None:
        created_sessions.append(session_id)
        await asyncio.sleep(60)

    async def _panel_poll_worker(panel_id: str) -> None:
        created_panels.append(panel_id)
        await asyncio.sleep(60)

    channel._session_watch_worker = _session_watch_worker
    channel._panel_poll_worker = _panel_poll_worker

    try:
        await channel._reconcile_transport_mode("fallback")
        await asyncio.sleep(0)

        assert channel._transport_mode == "fallback"
        assert list(channel._session_fallback_tasks) == ["s1"]
        assert list(channel._panel_fallback_tasks) == ["p1"]
        assert created_sessions == []
        assert created_panels == []
        assert stale_task.cancelled()

        channel._session_set.add("s2")
        channel._panel_set.add("p2")
        await channel._reconcile_transport_mode("fallback")
        await asyncio.sleep(0)

        assert set(channel._session_fallback_tasks) == {"s1", "s2"}
        assert set(channel._panel_fallback_tasks) == {"p1", "p2"}
        assert created_sessions == ["s2"]
        assert created_panels == ["p2"]

        await channel._reconcile_transport_mode("socket")
        await asyncio.sleep(0)

        assert channel._transport_mode == "socket"
        assert channel._session_fallback_tasks == {}
        assert channel._panel_fallback_tasks == {}
    finally:
        for task in [session_task, panel_task, stale_task]:
            task.cancel()
        await asyncio.gather(session_task, panel_task, stale_task, return_exceptions=True)
