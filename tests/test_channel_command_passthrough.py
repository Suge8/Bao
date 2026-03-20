from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from bao.bus.queue import MessageBus
from bao.channels._dingtalk_inbound import _DingTalkInboundPayload
from bao.channels.dingtalk import DingTalkChannel
from bao.channels.discord import DiscordChannel
from bao.channels.imessage import IMessageChannel
from bao.channels.qq import QQChannel
from bao.channels.slack import SlackChannel
from bao.channels.whatsapp import WhatsAppChannel
from bao.config.schema import (
    DingTalkConfig,
    DiscordConfig,
    IMessageConfig,
    QQConfig,
    SlackConfig,
    WhatsAppConfig,
)


@pytest.mark.asyncio
async def test_discord_slash_command_passes_through_to_core() -> None:
    channel = DiscordChannel(DiscordConfig(enabled=True, token=SecretStr("x")), MagicMock())
    channel._handle_message = AsyncMock()

    await channel._handle_message_create(
        {
            "author": {"id": "u1"},
            "channel_id": "c1",
            "content": "/memory",
            "attachments": [],
        }
    )

    inbound = channel._handle_message.await_args.args[0]
    assert inbound.content == "/memory"


@pytest.mark.asyncio
async def test_slack_slash_command_passes_through_to_core() -> None:
    channel = SlackChannel(
        SlackConfig(enabled=True, bot_token=SecretStr("x"), app_token=SecretStr("y")),
        MagicMock(),
    )
    channel._web_client = SimpleNamespace(reactions_add=AsyncMock())
    channel._handle_message = AsyncMock()

    client = SimpleNamespace(send_socket_mode_response=AsyncMock())
    request = SimpleNamespace(
        type="events_api",
        envelope_id="env-1",
        payload={
            "event": {
                "type": "message",
                "user": "U1",
                "channel": "D1",
                "text": "/memory",
                "channel_type": "im",
                "ts": "1700000000.1",
            }
        },
    )

    await channel._on_socket_request(client, request)

    inbound = channel._handle_message.await_args.args[0]
    assert inbound.content == "/memory"


@pytest.mark.asyncio
async def test_qq_slash_command_passes_through_to_core() -> None:
    channel = QQChannel(QQConfig(enabled=True), MessageBus())
    channel._handle_message = AsyncMock()

    data = SimpleNamespace(
        id="m1",
        author=SimpleNamespace(id="u1"),
        content="/memory",
    )

    await channel._on_message(data)

    inbound = channel._handle_message.await_args.args[0]
    assert inbound.content == "/memory"


@pytest.mark.asyncio
async def test_dingtalk_slash_command_passes_through_to_core() -> None:
    channel = DingTalkChannel(DingTalkConfig(enabled=True), MessageBus())
    channel._handle_message = AsyncMock()

    await channel._on_message(
        _DingTalkInboundPayload(
            content="/memory",
            sender_id="u1",
            sender_name="Alice",
        )
    )

    inbound = channel._handle_message.await_args.args[0]
    assert inbound.content == "/memory"


@pytest.mark.asyncio
async def test_whatsapp_slash_command_passes_through_to_core() -> None:
    channel = WhatsAppChannel(WhatsAppConfig(enabled=True), MessageBus())
    channel._handle_message = AsyncMock()

    await channel._handle_bridge_event_message(
        {
            "id": "m1",
            "sender": "123@c.us",
            "content": "/memory",
            "isGroup": False,
        }
    )

    inbound = channel._handle_message.await_args.args[0]
    assert inbound.content == "/memory"


@pytest.mark.asyncio
async def test_imessage_slash_command_passes_through_to_core() -> None:
    channel = IMessageChannel(IMessageConfig(enabled=True), MessageBus())
    channel._query_new = lambda: [(21, "/memory", "+123456", "chat-a")]
    channel._query_attachments = lambda _rowids: {}
    channel._handle_message = AsyncMock()

    await channel._poll()

    inbound = channel._handle_message.await_args.args[0]
    assert inbound.content == "/memory"
