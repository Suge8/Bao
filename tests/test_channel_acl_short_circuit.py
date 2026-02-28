from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bao.channels.telegram import TelegramChannel
from bao.channels.whatsapp import WhatsAppChannel
from bao.config.schema import TelegramConfig, WhatsAppConfig


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
