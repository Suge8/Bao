from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from bao.channels.telegram import TelegramChannel
from bao.config.schema import TelegramConfig
from tests._telegram_channel_testkit import TelegramUpdateOptions, _make_telegram_update


@pytest.mark.asyncio
async def test_telegram_forward_command_keeps_topic_session_metadata_without_reply_context() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), MagicMock())
    channel._handle_message = AsyncMock()

    reply = SimpleNamespace(text="older message", message_id=2, from_user=SimpleNamespace(id=1))
    update = _make_telegram_update(
        TelegramUpdateOptions(text="/new", reply_to_message=reply, message_thread_id=42)
    )

    await channel._forward_command(update, None)

    inbound = channel._handle_message.await_args.args[0]
    assert inbound.content == "/new"
    assert inbound.metadata["session_key"] == "telegram:-100123:topic:42"
    assert inbound.metadata["reply_to_message_id"] == 2


@pytest.mark.asyncio
async def test_telegram_on_message_adds_reply_text_context() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), allow_from=["123"], group_policy="open"),
        MagicMock(),
    )
    channel._app = SimpleNamespace(bot=SimpleNamespace(get_me=AsyncMock(), send_chat_action=AsyncMock()))
    channel._handle_message = AsyncMock()

    reply = SimpleNamespace(text="Hello", caption=None, message_id=2, from_user=SimpleNamespace(id=1))
    await channel._on_message(
        _make_telegram_update(TelegramUpdateOptions(text="translate this", reply_to_message=reply)),
        None,
    )

    inbound = channel._handle_message.await_args.args[0]
    assert inbound.content.startswith("[Reply to: Hello]")
    assert "translate this" in inbound.content


@pytest.mark.asyncio
async def test_telegram_on_message_attaches_reply_media_and_caption(monkeypatch, tmp_path) -> None:
    media_dir = tmp_path / "telegram"
    media_dir.mkdir(parents=True)
    monkeypatch.setattr("bao.channels.telegram.get_media_dir", lambda _channel=None: media_dir)

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), allow_from=["123"], group_policy="open"),
        MagicMock(),
    )
    bot = SimpleNamespace(
        get_me=AsyncMock(),
        get_file=AsyncMock(return_value=SimpleNamespace(download_to_drive=AsyncMock(return_value=None))),
        send_chat_action=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)
    channel._handle_message = AsyncMock()

    reply = SimpleNamespace(
        text=None,
        caption="A cute cat",
        photo=[SimpleNamespace(file_id="cat_fid", mime_type="image/jpeg")],
        document=None,
        voice=None,
        audio=None,
        video=None,
        video_note=None,
        animation=None,
        message_id=2,
        from_user=SimpleNamespace(id=1),
    )
    await channel._on_message(
        _make_telegram_update(
            TelegramUpdateOptions(text="what breed is this?", reply_to_message=reply)
        ),
        None,
    )

    inbound = channel._handle_message.await_args.args[0]
    assert "[Reply to: A cute cat]" in inbound.content
    assert len(inbound.media) == 1
    assert Path(inbound.media[0]).name.startswith("cat_fid")


@pytest.mark.asyncio
async def test_telegram_on_message_uses_reply_media_placeholder_when_no_reply_text(monkeypatch, tmp_path) -> None:
    media_dir = tmp_path / "telegram"
    media_dir.mkdir(parents=True)
    monkeypatch.setattr("bao.channels.telegram.get_media_dir", lambda _channel=None: media_dir)

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), allow_from=["123"], group_policy="open"),
        MagicMock(),
    )
    bot = SimpleNamespace(
        get_me=AsyncMock(),
        get_file=AsyncMock(return_value=SimpleNamespace(download_to_drive=AsyncMock(return_value=None))),
        send_chat_action=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)
    channel._handle_message = AsyncMock()

    reply = SimpleNamespace(
        text=None,
        caption=None,
        photo=[SimpleNamespace(file_id="reply_photo_fid", mime_type="image/jpeg")],
        document=None,
        voice=None,
        audio=None,
        video=None,
        video_note=None,
        animation=None,
        message_id=2,
        from_user=SimpleNamespace(id=1),
    )
    await channel._on_message(
        _make_telegram_update(
            TelegramUpdateOptions(text="what is the image?", reply_to_message=reply)
        ),
        None,
    )

    inbound = channel._handle_message.await_args.args[0]
    assert inbound.content.startswith("[Reply to: [image:")
    assert len(inbound.media) == 1


@pytest.mark.asyncio
async def test_telegram_on_message_reply_media_download_failure_skips_reply_tag() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), allow_from=["123"], group_policy="open"),
        MagicMock(),
    )
    channel._app = SimpleNamespace(
        bot=SimpleNamespace(get_me=AsyncMock(), get_file=None, send_chat_action=AsyncMock())
    )
    channel._handle_message = AsyncMock()

    reply = SimpleNamespace(
        text=None,
        caption=None,
        photo=[SimpleNamespace(file_id="x", mime_type="image/jpeg")],
        document=None,
        voice=None,
        audio=None,
        video=None,
        video_note=None,
        animation=None,
        message_id=2,
        from_user=SimpleNamespace(id=1),
    )
    await channel._on_message(
        _make_telegram_update(TelegramUpdateOptions(text="what is this?", reply_to_message=reply)),
        None,
    )

    inbound = channel._handle_message.await_args.args[0]
    assert inbound.content == "what is this?"
    assert inbound.media == []
