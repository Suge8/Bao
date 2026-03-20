from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import BadRequest, NetworkError

from bao.bus.events import OutboundMessage
from tests._telegram_channel_testkit import build_channel


@pytest.mark.asyncio
async def test_telegram_network_error_does_not_fallback_to_plain_resend() -> None:
    channel = build_channel()
    bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=NetworkError("httpx.ConnectError")),
        edit_message_text=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    with pytest.raises(NetworkError):
        await channel.send(
            OutboundMessage(
                channel="telegram",
                chat_id="12345",
                content="这是一个足够长的进度句子，会先发出去，顺手把上下文也先梳理一下。",
                metadata={"_progress": True},
            )
        )

    assert bot.send_message.await_count == 1
    assert bot.edit_message_text.await_count == 0


@pytest.mark.asyncio
async def test_telegram_parse_error_falls_back_to_plain_send_once() -> None:
    channel = build_channel()
    bot = SimpleNamespace(
        send_message=AsyncMock(
            side_effect=[
                BadRequest("Can't parse entities"),
                SimpleNamespace(message_id=99),
            ]
        ),
        edit_message_text=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="**这是一个足够长的 Markdown 进度句子，会先触发 HTML 发送。**",
            metadata={"_progress": True},
        )
    )

    assert bot.send_message.await_count == 2
    first = bot.send_message.await_args_list[0].kwargs
    second = bot.send_message.await_args_list[1].kwargs
    assert first["parse_mode"] == "HTML"
    assert "parse_mode" not in second


@pytest.mark.asyncio
async def test_telegram_final_send_network_error_is_not_retried() -> None:
    channel = build_channel()
    bot = SimpleNamespace(
        send_message=AsyncMock(
            side_effect=[
                SimpleNamespace(message_id=321),
                NetworkError("httpx.ConnectError"),
            ]
        ),
        edit_message_text=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    progress = "这是一个足够长的进度句子，会先发出去，顺手把上下文也先梳理一下。"
    final = f"{progress}然后再补一句结论。"

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content=progress,
            metadata={"_progress": True},
        )
    )

    with pytest.raises(NetworkError):
        await channel.send(OutboundMessage(channel="telegram", chat_id="12345", content=final))

    assert bot.send_message.await_count == 2
    assert bot.edit_message_text.await_count == 0


@pytest.mark.asyncio
async def test_telegram_edit_message_not_modified_is_ignored() -> None:
    channel = build_channel()
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
        edit_message_text=AsyncMock(side_effect=BadRequest("Message is not modified")),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel._update_progress_text("12345", 321, "相同文本")

    assert bot.send_message.await_count == 0
    assert bot.edit_message_text.await_count == 1
