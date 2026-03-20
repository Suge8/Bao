from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bao.bus.events import OutboundMessage
from tests._telegram_channel_testkit import build_channel


@pytest.mark.asyncio
async def test_telegram_send_ignores_bool_reply_to() -> None:
    channel = build_channel(reply_to_message=True)
    channel._app = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))

    msg = OutboundMessage(
        channel="telegram",
        chat_id="12345",
        content="hello",
        reply_to=True,
    )
    await channel.send(msg)

    kwargs = channel._app.bot.send_message.await_args.kwargs
    assert kwargs["reply_parameters"] is None


@pytest.mark.asyncio
async def test_telegram_progress_is_buffered_before_final_send() -> None:
    channel = build_channel()
    bot = SimpleNamespace(send_message=AsyncMock(), edit_message_text=AsyncMock())
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(OutboundMessage(channel="telegram", chat_id="12345", content="你", metadata={"_progress": True}))
    await channel.send(OutboundMessage(channel="telegram", chat_id="12345", content="好", metadata={"_progress": True}))
    await channel.send(OutboundMessage(channel="telegram", chat_id="12345", content="你好"))

    assert bot.send_message.await_count == 1
    assert bot.edit_message_text.await_count == 0
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 12345
    assert kwargs["text"] == "你好"


@pytest.mark.asyncio
async def test_telegram_final_only_sends_tail_after_progress_flush() -> None:
    channel = build_channel()
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
        edit_message_text=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    progress = "这是一个足够长的进度句子，会先发出去，顺手把上下文也先梳理一下。"
    final = f"{progress}然后再补一句结论。"

    await channel.send(OutboundMessage(channel="telegram", chat_id="12345", content=progress, metadata={"_progress": True}))
    await channel.send(OutboundMessage(channel="telegram", chat_id="12345", content=final))

    assert bot.send_message.await_count == 2
    assert bot.edit_message_text.await_count == 0
    assert bot.send_message.await_args_list[0].kwargs["text"] == progress
    assert bot.send_message.await_args_list[1].kwargs["text"] == "然后再补一句结论。"


@pytest.mark.asyncio
async def test_telegram_tool_hint_starts_new_editable_turn() -> None:
    channel = build_channel()
    bot = SimpleNamespace(
        send_message=AsyncMock(
            side_effect=[
                SimpleNamespace(message_id=321),
                SimpleNamespace(message_id=654),
                SimpleNamespace(message_id=987),
            ]
        ),
        edit_message_text=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(OutboundMessage(channel="telegram", chat_id="12345", content="我现在去看看。", metadata={"_progress": True}))
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="🔎 Search Web: latest ai news",
            metadata={"_progress": True, "_tool_hint": True},
        )
    )
    await channel.send(OutboundMessage(channel="telegram", chat_id="12345", content="整理好了，这是最终答案。"))

    assert bot.send_message.await_count == 3
    assert [call.kwargs["text"] for call in bot.send_message.await_args_list] == [
        "我现在去看看。",
        "🔎 Search Web: latest ai news",
        "整理好了，这是最终答案。",
    ]


@pytest.mark.asyncio
async def test_telegram_tool_hint_seals_main_scope_before_final_reply() -> None:
    channel = build_channel()
    bot = SimpleNamespace(
        send_message=AsyncMock(
            side_effect=[
                SimpleNamespace(message_id=321),
                SimpleNamespace(message_id=654),
                SimpleNamespace(message_id=987),
            ]
        ),
        edit_message_text=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="我现在去看看。",
            metadata={"_progress": True, "_progress_scope": "main:turn-1"},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="🔎 Search Web: latest ai news",
            metadata={"_progress": True, "_tool_hint": True, "_progress_scope": "tool:turn-1"},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="整理好了，这是最终答案。",
            metadata={"_progress_scope": "main:turn-1"},
        )
    )

    assert bot.send_message.await_count == 3
    assert bot.edit_message_text.await_count == 0
    assert [call.kwargs["text"] for call in bot.send_message.await_args_list] == [
        "我现在去看看。",
        "🔎 Search Web: latest ai news",
        "整理好了，这是最终答案。",
    ]


@pytest.mark.asyncio
async def test_telegram_multiple_tool_hints_still_keep_final_reply_below_hints() -> None:
    channel = build_channel()
    bot = SimpleNamespace(
        send_message=AsyncMock(
            side_effect=[
                SimpleNamespace(message_id=321),
                SimpleNamespace(message_id=654),
                SimpleNamespace(message_id=777),
                SimpleNamespace(message_id=987),
            ]
        ),
        edit_message_text=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="我现在去看看。",
            metadata={"_progress": True, "_progress_scope": "main:turn-1"},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="📨 Session Default: channel=imessage",
            metadata={"_progress": True, "_tool_hint": True, "_progress_scope": "tool:turn-1"},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="✉️ Send Notification: imessage:+61400",
            metadata={"_progress": True, "_tool_hint": True, "_progress_scope": "tool:turn-1"},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="已经发到 iMessage 目标会话了。",
            metadata={"_progress_scope": "main:turn-1"},
        )
    )

    assert bot.send_message.await_count == 4
    assert bot.edit_message_text.await_count == 0
    assert [call.kwargs["text"] for call in bot.send_message.await_args_list] == [
        "我现在去看看。",
        "📨 Session Default: channel=imessage",
        "✉️ Send Notification: imessage:+61400",
        "已经发到 iMessage 目标会话了。",
    ]


@pytest.mark.asyncio
async def test_telegram_progress_scope_keeps_main_and_subagent_turns_separate() -> None:
    channel = build_channel()
    bot = SimpleNamespace(
        send_message=AsyncMock(
            side_effect=[
                SimpleNamespace(message_id=321),
                SimpleNamespace(message_id=654),
                SimpleNamespace(message_id=987),
            ]
        ),
        edit_message_text=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="主回复进度，这是一段足够长的文字，用来创建主回复流式气泡。",
            metadata={"_progress": True, "_progress_scope": "main:turn-1"},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="子代理进度，这也是一段足够长的文字，用来创建独立的任务进度气泡。",
            metadata={"_progress": True, "_progress_scope": "subagent:t1"},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="主回复最终完成",
            metadata={"_progress_scope": "main:turn-1"},
        )
    )

    assert bot.send_message.await_count == 3
    assert bot.edit_message_text.await_count == 0
    assert [call.kwargs["text"] for call in bot.send_message.await_args_list] == [
        "主回复进度，这是一段足够长的文字，用来创建主回复流式气泡。",
        "子代理进度，这也是一段足够长的文字，用来创建独立的任务进度气泡。",
        "主回复最终完成",
    ]
