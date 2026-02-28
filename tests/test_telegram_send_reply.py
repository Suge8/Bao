from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bao.bus.events import OutboundMessage
from bao.channels.telegram import TelegramChannel
from bao.config.schema import TelegramConfig


@pytest.mark.asyncio
async def test_telegram_send_prefers_reply_to_over_metadata() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="t", reply_to_message=True), MagicMock()
    )
    bot = SimpleNamespace(send_message=AsyncMock())
    channel._app = SimpleNamespace(bot=bot)

    msg = OutboundMessage(
        channel="telegram",
        chat_id="12345",
        content="hello",
        reply_to="77",
        metadata={"message_id": "999"},
    )
    await channel.send(msg)

    assert bot.send_message.await_count == 1
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 12345
    assert kwargs["reply_parameters"].message_id == 77


@pytest.mark.asyncio
async def test_telegram_send_ignores_bool_reply_to() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token="t", reply_to_message=True), MagicMock()
    )
    bot = SimpleNamespace(send_message=AsyncMock())
    channel._app = SimpleNamespace(bot=bot)

    msg = OutboundMessage(channel="telegram", chat_id="12345", content="hello", reply_to=True)
    await channel.send(msg)

    assert bot.send_message.await_count == 1
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 12345
    assert kwargs["reply_parameters"] is None
