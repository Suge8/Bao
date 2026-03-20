from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bao.bus.events import OutboundMessage
from tests._telegram_channel_testkit import build_channel


@pytest.mark.asyncio
async def test_telegram_progress_send_keeps_message_thread_id() -> None:
    channel = build_channel()
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
        edit_message_text=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="topic progress",
            metadata={"_progress": True, "message_thread_id": 42},
        )
    )

    await channel._progress_handler.flush("12345", force=True)

    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["message_thread_id"] == 42


@pytest.mark.asyncio
async def test_telegram_reply_inferrs_topic_from_cached_thread_context() -> None:
    channel = build_channel(reply_to_message=True)
    bot = SimpleNamespace(send_message=AsyncMock(), edit_message_text=AsyncMock())
    channel._app = SimpleNamespace(bot=bot)
    channel._message_threads[("12345", 10)] = 42

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="hello",
            metadata={"message_id": 10},
        )
    )

    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["message_thread_id"] == 42
    assert kwargs["reply_parameters"].message_id == 10


@pytest.mark.asyncio
async def test_telegram_progress_does_not_stop_typing() -> None:
    channel = build_channel()
    bot = SimpleNamespace(send_message=AsyncMock(), edit_message_text=AsyncMock())
    channel._app = SimpleNamespace(bot=bot)
    channel._typing_tasks["12345"] = AsyncMock()

    with patch.object(channel, "_stop_typing") as stop_typing:
        await channel.send(
            OutboundMessage(
                channel="telegram",
                chat_id="12345",
                content="progress",
                metadata={"_progress": True},
            )
        )

    stop_typing.assert_not_called()


@pytest.mark.asyncio
async def test_telegram_send_prefers_reply_to_over_metadata() -> None:
    channel = build_channel(reply_to_message=True)
    channel._app = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))

    msg = OutboundMessage(
        channel="telegram",
        chat_id="12345",
        content="hello",
        reply_to="77",
        metadata={"message_id": "999"},
    )
    await channel.send(msg)

    kwargs = channel._app.bot.send_message.await_args.kwargs
    assert kwargs["reply_parameters"].message_id == 77
