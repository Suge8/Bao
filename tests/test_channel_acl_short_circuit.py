from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bao.channels.discord import DiscordChannel
from bao.channels.telegram import TelegramChannel
from bao.channels.whatsapp import WhatsAppChannel
from bao.config.schema import DiscordConfig, TelegramConfig, WhatsAppConfig


def _discord_payload(
    *,
    content: str,
    guild_id: str | None = "g1",
    mentions: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "m1",
        "channel_id": "c1",
        "content": content,
        "author": {"id": "123", "bot": False},
        "mentions": mentions or [],
        "attachments": [],
    }
    if guild_id is not None:
        payload["guild_id"] = guild_id
    return payload


@pytest.mark.asyncio
async def test_telegram_acl_blocks_media_download_before_get_file() -> None:
    bus = MagicMock()
    cfg = TelegramConfig(enabled=True, token="token", allow_from=["999"])
    channel = TelegramChannel(cfg, bus)

    bot = SimpleNamespace(get_file=AsyncMock())
    channel._app = SimpleNamespace(bot=bot)

    message = SimpleNamespace(
        chat_id=12345,
        text=None,
        caption=None,
        photo=[SimpleNamespace(file_id="photo123", mime_type="image/jpeg")],
        voice=None,
        audio=None,
        document=None,
        message_id=77,
        chat=SimpleNamespace(type="private"),
    )
    user = SimpleNamespace(id=123, username=None, first_name="u")
    update = SimpleNamespace(message=message, effective_user=user)

    await channel._on_message(update, None)

    bot.get_file.assert_not_awaited()
    assert "123" not in channel._chat_ids


@pytest.mark.asyncio
async def test_telegram_acl_accepts_numeric_id_from_composite_sender() -> None:
    bus = MagicMock()
    cfg = TelegramConfig(enabled=True, token="token", allow_from=["123"])
    channel = TelegramChannel(cfg, bus)

    channel._handle_message = AsyncMock()
    message = SimpleNamespace(
        chat_id=123,
        text="hi",
        caption=None,
        photo=None,
        voice=None,
        audio=None,
        document=None,
        message_id=77,
        chat=SimpleNamespace(type="private"),
    )
    user = SimpleNamespace(id=123, username="alice", first_name="u")
    update = SimpleNamespace(message=message, effective_user=user)

    await channel._on_message(update, None)

    channel._handle_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_whatsapp_acl_blocks_media_save_before_write() -> None:
    bus = MagicMock()
    cfg = WhatsAppConfig(enabled=True, allow_from=["999"])
    channel = WhatsAppChannel(cfg, bus)

    channel._save_media = MagicMock(return_value=["/tmp/x"])
    channel._handle_message = AsyncMock()

    payload = {
        "type": "message",
        "pn": "123@s.whatsapp.net",
        "sender": "room@g.us",
        "participant": "123@s.whatsapp.net",
        "isGroup": True,
        "content": "hi",
        "media": {"data": "aGVsbG8=", "mimetype": "text/plain", "filename": "a.txt"},
    }

    await channel._handle_bridge_message(json.dumps(payload))

    channel._save_media.assert_not_called()
    channel._handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_whatsapp_dedup_skips_duplicate_message_id() -> None:
    bus = MagicMock()
    cfg = WhatsAppConfig(enabled=True)
    channel = WhatsAppChannel(cfg, bus)
    channel._handle_message = AsyncMock()

    payload = {
        "type": "message",
        "id": "dup-1",
        "pn": "123@s.whatsapp.net",
        "sender": "123@s.whatsapp.net",
        "participant": "",
        "isGroup": False,
        "content": "hi",
    }

    await channel._handle_bridge_message(json.dumps(payload))
    await channel._handle_bridge_message(json.dumps(payload))

    assert channel._handle_message.await_count == 1


def test_whatsapp_acl_does_not_split_sender_tokens() -> None:
    cfg = WhatsAppConfig(enabled=True, allow_from=["999"])
    channel = WhatsAppChannel(cfg, MagicMock())

    assert channel.is_allowed("123|999") is False


@pytest.mark.asyncio
async def test_whatsapp_without_message_id_does_not_dedup() -> None:
    bus = MagicMock()
    cfg = WhatsAppConfig(enabled=True)
    channel = WhatsAppChannel(cfg, bus)
    channel._handle_message = AsyncMock()

    payload = {
        "type": "message",
        "pn": "123@s.whatsapp.net",
        "sender": "123@s.whatsapp.net",
        "participant": "",
        "isGroup": False,
        "content": "hi",
    }

    await channel._handle_bridge_message(json.dumps(payload))
    await channel._handle_bridge_message(json.dumps(payload))

    assert channel._handle_message.await_count == 2


@pytest.mark.asyncio
async def test_discord_group_policy_mention_blocks_unmentioned_guild_message() -> None:
    channel = DiscordChannel(
        DiscordConfig(enabled=True, token="token", allow_from=["123"], group_policy="mention"),
        MagicMock(),
    )
    channel._http = MagicMock()
    channel._bot_user_id = "999"
    channel._handle_message = AsyncMock()
    channel._start_typing = AsyncMock()

    await channel._handle_message_create(_discord_payload(content="hello everyone"))

    channel._handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_discord_group_policy_mention_accepts_mentions_array() -> None:
    channel = DiscordChannel(
        DiscordConfig(enabled=True, token="token", allow_from=["123"], group_policy="mention"),
        MagicMock(),
    )
    channel._http = MagicMock()
    channel._bot_user_id = "999"
    channel._handle_message = AsyncMock()
    channel._start_typing = AsyncMock()

    await channel._handle_message_create(
        _discord_payload(content="hello", mentions=[{"id": "999"}])
    )

    channel._handle_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_discord_group_policy_mention_accepts_inline_mention_syntax() -> None:
    channel = DiscordChannel(
        DiscordConfig(enabled=True, token="token", allow_from=["123"], group_policy="mention"),
        MagicMock(),
    )
    channel._http = MagicMock()
    channel._bot_user_id = "999"
    channel._handle_message = AsyncMock()
    channel._start_typing = AsyncMock()

    await channel._handle_message_create(_discord_payload(content="<@!999> hi"))

    channel._handle_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_discord_group_policy_open_accepts_plain_guild_message() -> None:
    channel = DiscordChannel(
        DiscordConfig(enabled=True, token="token", allow_from=["123"], group_policy="open"),
        MagicMock(),
    )
    channel._http = MagicMock()
    channel._handle_message = AsyncMock()
    channel._start_typing = AsyncMock()

    await channel._handle_message_create(_discord_payload(content="hello everyone"))

    channel._handle_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_discord_dm_ignores_group_policy() -> None:
    channel = DiscordChannel(
        DiscordConfig(enabled=True, token="token", allow_from=["123"], group_policy="mention"),
        MagicMock(),
    )
    channel._http = MagicMock()
    channel._handle_message = AsyncMock()
    channel._start_typing = AsyncMock()

    await channel._handle_message_create(_discord_payload(content="hello dm", guild_id=None))

    channel._handle_message.assert_awaited_once()
