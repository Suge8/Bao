# ruff: noqa: F403, F405
from __future__ import annotations

from tests._channel_lifecycle_testkit import *


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
