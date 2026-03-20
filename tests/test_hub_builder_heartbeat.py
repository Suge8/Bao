"""Heartbeat routing tests for bao.hub.builder."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import bao.hub.builder as mod
from bao.hub.builder import build_hub_stack
from tests._hub_builder_testkit import (
    FakeLifecycleChannels,
    apply_hub_stack_patches,
    build_stack_options,
    make_hub_config,
    set_channels,
)

pytestmark = pytest.mark.integration


def _build_stack_with_channels(channel_setup) -> tuple[object, MagicMock, MagicMock]:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()
    fake_agent.process_direct = AsyncMock(return_value="ok")
    config = make_hub_config()
    channel_setup(config)

    with apply_hub_stack_patches(
        mod,
        fake_agent=fake_agent,
        fake_bus=fake_bus,
        fake_channels=FakeLifecycleChannels(),
        patch_heartbeat=False,
    ):
        stack = build_hub_stack(config, MagicMock(), build_stack_options())
    return stack, fake_bus, fake_agent


def _awaited_process_direct_request(fake_agent: MagicMock):
    fake_agent.process_direct.assert_awaited_once()
    return fake_agent.process_direct.await_args.args[0]


@pytest.mark.asyncio
async def test_heartbeat_uses_whatsapp_jid_and_skips_discord_allow_from() -> None:
    stack, fake_bus, fake_agent = _build_stack_with_channels(
        lambda config: set_channels(
            config,
            whatsapp=["8613800138000"],
            discord=["discord-user-id"],
        )
    )

    await stack.heartbeat.on_execute("do tasks")
    request = _awaited_process_direct_request(fake_agent)
    assert request.channel == "whatsapp"
    assert request.chat_id == "8613800138000@s.whatsapp.net"
    assert request.profile_id == ""

    await stack.heartbeat.on_notify("notify")
    fake_bus.publish_outbound.assert_awaited_once()
    outbound = fake_bus.publish_outbound.await_args.args[0]
    assert outbound.channel == "whatsapp"
    assert outbound.chat_id == "8613800138000@s.whatsapp.net"


@pytest.mark.asyncio
async def test_heartbeat_skips_telegram_username_target() -> None:
    stack, _fake_bus, fake_agent = _build_stack_with_channels(
        lambda config: set_channels(config, telegram=["some_username"], feishu=["ou_123"])
    )

    await stack.heartbeat.on_execute("do tasks")
    request = _awaited_process_direct_request(fake_agent)
    assert request.channel == "feishu"
    assert request.chat_id == "ou_123"


@pytest.mark.asyncio
async def test_heartbeat_uses_later_valid_target_from_shared_target_list() -> None:
    stack, fake_bus, fake_agent = _build_stack_with_channels(
        lambda config: set_channels(
            config,
            telegram=["some_username", "-1001234567890"],
            feishu=["ou_123"],
        )
    )

    await stack.heartbeat.on_execute("do tasks")
    request = _awaited_process_direct_request(fake_agent)
    assert request.channel == "telegram"
    assert request.chat_id == "-1001234567890"

    await stack.heartbeat.on_notify("notify")
    fake_bus.publish_outbound.assert_awaited_once()
    outbound = fake_bus.publish_outbound.await_args.args[0]
    assert outbound.channel == "telegram"
    assert outbound.chat_id == "-1001234567890"


@pytest.mark.asyncio
async def test_heartbeat_without_primary_proactive_target_falls_back_to_cli_and_skips_notify() -> None:
    stack, fake_bus, fake_agent = _build_stack_with_channels(
        lambda config: set_channels(config, telegram=["some_username"])
    )

    await stack.heartbeat.on_execute("do tasks")
    request = _awaited_process_direct_request(fake_agent)
    assert request.channel == "cli"
    assert request.chat_id == "direct"

    await stack.heartbeat.on_notify("notify")
    fake_bus.publish_outbound.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_accepts_negative_telegram_chat_id() -> None:
    stack, _fake_bus, fake_agent = _build_stack_with_channels(
        lambda config: set_channels(
            config,
            telegram=["-1001234567890"],
            feishu=["ou_123"],
        )
    )

    await stack.heartbeat.on_execute("do tasks")
    request = _awaited_process_direct_request(fake_agent)
    assert request.channel == "telegram"
    assert request.chat_id == "-1001234567890"


@pytest.mark.asyncio
async def test_heartbeat_accepts_telegram_composite_target() -> None:
    stack, _fake_bus, fake_agent = _build_stack_with_channels(
        lambda config: set_channels(config, telegram=["abc45879|6374137703"])
    )

    await stack.heartbeat.on_execute("do tasks")
    request = _awaited_process_direct_request(fake_agent)
    assert request.channel == "telegram"
    assert request.chat_id == "6374137703"
