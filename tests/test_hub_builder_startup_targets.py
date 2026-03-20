"""Startup greeting target selection tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bao.hub.builder import DesktopStartupMessage, send_startup_greeting
from tests._hub_builder_testkit import make_hub_config, set_channels, startup_options

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_startup_greeting_ready_stage_skips_external_publish_even_with_targets() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()
    config = make_hub_config()
    set_channels(config, telegram=["-1001234567890"], feishu=["ou_123"])

    with patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"):
        await send_startup_greeting(fake_agent, fake_bus, startup_options(config))

    fake_bus.publish_outbound.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_greeting_skips_telegram_username_target() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()
    config = make_hub_config()
    set_channels(config, telegram=["some_username"], feishu=["ou_123"])

    with (
        patch("bao.hub._builder_startup.asyncio.sleep", new=AsyncMock()),
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="lang_select"),
        patch("bao.config.onboarding.LANG_PICKER", "picker"),
    ):
        await send_startup_greeting(fake_agent, fake_bus, startup_options(config))

    assert fake_bus.publish_outbound.await_count == 1
    outbound = fake_bus.publish_outbound.await_args.args[0]
    assert outbound.channel == "feishu"
    assert outbound.chat_id == "ou_123"


@pytest.mark.asyncio
async def test_startup_greeting_accepts_negative_telegram_chat_id() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()
    config = make_hub_config()
    set_channels(config, telegram=["-1001234567890"])

    with (
        patch("bao.hub._builder_startup.asyncio.sleep", new=AsyncMock()),
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="lang_select"),
        patch("bao.config.onboarding.LANG_PICKER", "picker"),
    ):
        await send_startup_greeting(fake_agent, fake_bus, startup_options(config))

    assert fake_bus.publish_outbound.await_count == 1
    outbound = fake_bus.publish_outbound.await_args.args[0]
    assert outbound.channel == "telegram"
    assert outbound.chat_id == "-1001234567890"


@pytest.mark.asyncio
async def test_startup_greeting_accepts_telegram_composite_target() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()
    config = make_hub_config()
    set_channels(config, telegram=["abc45879|6374137703"])

    with (
        patch("bao.hub._builder_startup.asyncio.sleep", new=AsyncMock()),
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="lang_select"),
        patch("bao.config.onboarding.LANG_PICKER", "picker"),
    ):
        await send_startup_greeting(fake_agent, fake_bus, startup_options(config))

    assert fake_bus.publish_outbound.await_count == 1
    outbound = fake_bus.publish_outbound.await_args.args[0]
    assert outbound.channel == "telegram"
    assert outbound.chat_id == "6374137703"


@pytest.mark.asyncio
async def test_startup_greeting_onboarding_desktop_not_blocked_by_external_publish() -> None:
    fake_bus = MagicMock()
    publish_started = asyncio.Event()
    release_publish = asyncio.Event()

    async def _publish_side_effect(_msg):
        publish_started.set()
        await release_publish.wait()

    fake_bus.publish_outbound = AsyncMock(side_effect=_publish_side_effect)
    fake_agent = MagicMock()
    desktop_called = asyncio.Event()

    async def _on_desktop(_message: DesktopStartupMessage) -> None:
        desktop_called.set()

    on_desktop = AsyncMock(side_effect=_on_desktop)
    config = make_hub_config()
    set_channels(config, imessage=["13800138000"])

    with (
        patch("bao.hub._builder_startup.asyncio.sleep", new=AsyncMock()),
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="lang_select"),
        patch("bao.config.onboarding.LANG_PICKER", "picker"),
    ):
        run_task = asyncio.create_task(
            send_startup_greeting(
                fake_agent,
                fake_bus,
                startup_options(config, on_desktop_startup_message=on_desktop),
            )
        )
        await publish_started.wait()
        await asyncio.wait_for(desktop_called.wait(), timeout=0.5)
        release_publish.set()
        await run_task

    on_desktop.assert_awaited_once_with(
        DesktopStartupMessage(
            content="picker",
            role="assistant",
            entrance_style="assistantReceived",
        )
    )
    assert fake_bus.publish_outbound.await_count == 1


@pytest.mark.asyncio
async def test_startup_greeting_waits_for_channel_ready_when_provided() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    ready_evt = asyncio.Event()
    sent: list[object] = []

    class FakeRuntimeChannels:
        async def wait_started(self) -> None:
            return None

        async def wait_ready(self, _name: str) -> None:
            await ready_evt.wait()

        async def send_outbound(self, msg) -> None:
            sent.append(msg)

    fake_agent = MagicMock()
    config = make_hub_config()
    set_channels(config, feishu=["ou_123"])

    with (
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="lang_select"),
        patch("bao.config.onboarding.LANG_PICKER", "picker"),
    ):
        task = asyncio.create_task(
            send_startup_greeting(
                fake_agent,
                fake_bus,
                startup_options(config, channels=FakeRuntimeChannels()),
            )
        )
        await asyncio.sleep(0)
        assert fake_bus.publish_outbound.await_count == 0
        assert sent == []
        ready_evt.set()
        await asyncio.wait_for(task, timeout=0.5)

    assert fake_bus.publish_outbound.await_count == 0
    assert len(sent) == 1
