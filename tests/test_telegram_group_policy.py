from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from bao.channels.telegram import TelegramChannel
from bao.config.schema import TelegramConfig
from tests._telegram_channel_testkit import TelegramUpdateOptions, _make_telegram_update


def test_telegram_group_policy_defaults_to_mention() -> None:
    assert TelegramConfig().group_policy == "mention"


@pytest.mark.asyncio
async def test_telegram_group_policy_mention_ignores_unmentioned_group_message() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), allow_from=["123"], group_policy="mention"),
        MagicMock(),
    )
    channel._app = SimpleNamespace(
        bot=SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(id=999, username="bao_bot")))
    )
    channel._handle_message = AsyncMock()

    await channel._on_message(_make_telegram_update(TelegramUpdateOptions(text="hello everyone")), None)

    channel._handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_group_policy_mention_accepts_entity_mention_and_caches_identity() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), allow_from=["123"], group_policy="mention"),
        MagicMock(),
    )
    bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(id=999, username="bao_bot")))
    channel._app = SimpleNamespace(bot=bot)
    channel._handle_message = AsyncMock()

    mention = SimpleNamespace(type="mention", offset=0, length=8)
    await channel._on_message(
        _make_telegram_update(TelegramUpdateOptions(text="@bao_bot hi", entities=[mention])),
        None,
    )
    await channel._on_message(
        _make_telegram_update(TelegramUpdateOptions(text="@bao_bot again", entities=[mention])),
        None,
    )

    assert channel._handle_message.await_count == 2
    assert bot.get_me.await_count == 1


@pytest.mark.asyncio
async def test_telegram_group_policy_open_accepts_plain_group_message() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), allow_from=["123"], group_policy="open"),
        MagicMock(),
    )
    channel._app = SimpleNamespace(bot=SimpleNamespace(get_me=AsyncMock()))
    channel._handle_message = AsyncMock()

    await channel._on_message(_make_telegram_update(TelegramUpdateOptions(text="hello group")), None)

    channel._handle_message.assert_awaited_once()
    channel._app.bot.get_me.assert_not_awaited()
