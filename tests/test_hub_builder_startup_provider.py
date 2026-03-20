"""Startup greeting provider and activity tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bao.hub.builder import DesktopStartupMessage, send_startup_greeting
from tests._hub_builder_testkit import make_hub_config, set_channels, startup_options

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_startup_greeting_uses_provider_chat_only() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()
    fake_agent.model = "right-gpt/gpt-5.3-codex"
    fake_agent.max_tokens = 4096
    fake_agent.temperature = 0.1
    fake_agent.provider = MagicMock()
    fake_agent.provider.chat = AsyncMock(return_value=MagicMock(content="hello"))
    fake_agent.process_direct = AsyncMock(return_value="should-not-be-used")
    on_desktop = AsyncMock()

    config = make_hub_config()
    set_channels(config, feishu=["ou_123"])

    with (
        patch("bao.hub._builder_startup.asyncio.sleep", new=AsyncMock()),
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"),
    ):
        await send_startup_greeting(
            fake_agent,
            fake_bus,
            startup_options(config, on_desktop_startup_message=on_desktop),
        )

    fake_agent.provider.chat.assert_awaited_once()
    await_args = fake_agent.provider.chat.await_args
    assert await_args is not None
    request = await_args.args[0]
    assert request.temperature == 0.7
    assert request.source == "startup"
    messages = request.messages
    assert "Respond in 中文" in messages[0]["content"]
    assert messages[1]["content"] == '{"event":"system.user_online"}'
    assert "## Runtime (actual host)" in messages[0]["content"]
    assert "Channel: desktop | Chat: local" in messages[0]["content"]
    fake_agent.process_direct.assert_not_awaited()
    fake_bus.publish_outbound.assert_not_awaited()
    on_desktop.assert_awaited_once_with(
        DesktopStartupMessage(content="hello", role="assistant", entrance_style="greeting")
    )


@pytest.mark.asyncio
async def test_startup_greeting_prefers_utility_model_when_configured() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()

    main_provider = MagicMock()
    main_provider.chat = AsyncMock(return_value=MagicMock(content="main"))
    utility_provider = MagicMock()
    utility_provider.chat = AsyncMock(return_value=MagicMock(content="hello"))

    fake_agent = MagicMock()
    fake_agent.model = "main/model"
    fake_agent.provider = main_provider
    fake_agent._utility_provider = utility_provider
    fake_agent._utility_model = "utility/model"
    fake_agent.process_direct = AsyncMock(return_value="should-not-be-used")
    on_desktop = AsyncMock()

    config = make_hub_config()
    set_channels(config, feishu=["ou_123"])

    with (
        patch("bao.hub._builder_startup.asyncio.sleep", new=AsyncMock()),
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"),
    ):
        await send_startup_greeting(
            fake_agent,
            fake_bus,
            startup_options(config, on_desktop_startup_message=on_desktop),
        )

    utility_provider.chat.assert_awaited_once()
    main_provider.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_greeting_ready_stage_skips_external_targets() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()
    fake_agent.model = "right-gpt/gpt-5.3-codex"
    fake_agent.provider = MagicMock()
    fake_agent.provider.chat = AsyncMock(return_value=MagicMock(content="unused"))
    fake_agent.process_direct = AsyncMock(return_value="fallback")

    config = make_hub_config()
    set_channels(config, imessage=["13800138000"])

    with (
        patch("bao.hub._builder_startup.asyncio.sleep", new=AsyncMock()),
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"),
    ):
        await send_startup_greeting(fake_agent, fake_bus, startup_options(config))

    fake_agent.provider.chat.assert_not_awaited()
    assert fake_bus.publish_outbound.await_count == 0


@pytest.mark.asyncio
async def test_startup_greeting_emits_planned_channels_to_activity_callback() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()
    fake_agent.model = "right-gpt/gpt-5.3-codex"
    fake_agent.provider = MagicMock()
    fake_agent.provider.chat = AsyncMock(return_value=MagicMock(content="unused"))
    fake_agent.process_direct = AsyncMock(return_value="fallback")

    on_desktop = AsyncMock()
    on_activity = AsyncMock()
    config = make_hub_config()
    set_channels(config, imessage=["13800138000"])

    async def _fake_generate(
        request,
    ) -> str:
        assert request.system_prompt
        assert request.prompt
        assert request.chat_id
        return "desktop-hi" if request.channel == "desktop" else "imessage-hi"

    with (
        patch("bao.hub._builder_startup.asyncio.sleep", new=AsyncMock()),
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"),
        patch("bao.hub._builder_startup._generate_startup_greeting", new=_fake_generate),
    ):
        await send_startup_greeting(
            fake_agent,
            fake_bus,
            startup_options(
                config,
                on_desktop_startup_message=on_desktop,
                on_startup_activity=on_activity,
            ),
        )

    assert any(
        call.args
        and call.args[0].get("status") == "running"
        and call.args[0].get("channelKeys") == ["desktop"]
        and call.args[0].get("sessionKeys") == ["desktop:local"]
        for call in on_activity.await_args_list
    )
