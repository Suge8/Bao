"""Startup greeting resilience and failure-path tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bao.hub.builder import DesktopStartupMessage, send_startup_greeting
from tests._hub_builder_testkit import make_hub_config, set_channels, startup_options

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_startup_greeting_cancellation_cancels_desktop_callback() -> None:
    fake_bus = MagicMock()
    publish_started = asyncio.Event()
    publish_released = asyncio.Event()

    async def _publish_side_effect(_msg):
        publish_started.set()
        await publish_released.wait()

    fake_bus.publish_outbound = AsyncMock(side_effect=_publish_side_effect)
    fake_agent = MagicMock()
    fake_agent.model = "right-gpt/gpt-5.3-codex"
    fake_agent.provider = MagicMock()
    fake_agent.process_direct = AsyncMock(return_value="fallback")

    desktop_started = asyncio.Event()
    desktop_cancelled = asyncio.Event()

    async def _on_desktop(_message: DesktopStartupMessage) -> None:
        desktop_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            desktop_cancelled.set()
            raise

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
        await desktop_started.wait()
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task
        await asyncio.wait_for(desktop_cancelled.wait(), timeout=0.5)
        publish_released.set()


@pytest.mark.asyncio
async def test_startup_greeting_provider_failure_is_isolated() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()
    fake_agent.model = "right-gpt/gpt-5.3-codex"
    fake_agent.max_tokens = 4096
    fake_agent.temperature = 0.1
    fake_agent.provider = MagicMock()
    fake_agent.provider.chat = AsyncMock(
        side_effect=[RuntimeError("first channel failed"), MagicMock(content="hello-second")]
    )
    fake_agent.process_direct = AsyncMock(return_value="should-not-be-used")
    on_desktop = AsyncMock()

    config = make_hub_config()
    set_channels(config, telegram=["-1001234567890"], feishu=["ou_123"])

    with (
        patch("bao.hub._builder_startup.asyncio.sleep", new=AsyncMock()),
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"),
    ):
        await send_startup_greeting(
            fake_agent,
            fake_bus,
            startup_options(config, on_desktop_startup_message=on_desktop),
        )

    assert fake_agent.provider.chat.await_count == 1
    fake_agent.process_direct.assert_not_awaited()
    fake_bus.publish_outbound.assert_not_awaited()
    on_desktop.assert_awaited_once_with(
        DesktopStartupMessage(
            content="我在呢，随时可以开干。",
            role="assistant",
            entrance_style="greeting",
        )
    )


@pytest.mark.asyncio
async def test_startup_greeting_provider_failure_falls_back_to_localized_copy() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()
    fake_agent.model = "right-gpt/gpt-5.3-codex"
    fake_agent.max_tokens = 4096
    fake_agent.temperature = 0.1
    fake_agent.provider = MagicMock()
    fake_agent.provider.chat = AsyncMock(side_effect=RuntimeError("provider down"))
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
    fake_agent.process_direct.assert_not_awaited()
    fake_bus.publish_outbound.assert_not_awaited()
    on_desktop.assert_awaited_once_with(
        DesktopStartupMessage(
            content="我在呢，随时可以开干。",
            role="assistant",
            entrance_style="greeting",
        )
    )


@pytest.mark.asyncio
async def test_startup_greeting_keeps_model_output_without_audit() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()
    fake_agent.model = "right-gpt/gpt-5.3-codex"
    fake_agent.max_tokens = 4096
    fake_agent.temperature = 0.1
    fake_agent.provider = MagicMock()
    fake_agent.provider.chat = AsyncMock(return_value=MagicMock(content="你是想让我帮你设置提醒吗？"))
    fake_agent.process_direct = AsyncMock(return_value="should-not-be-used")
    on_desktop = AsyncMock()

    config = make_hub_config()
    set_channels(config, feishu=["ou_123"])

    with (
        patch("bao.hub._builder_startup.asyncio.sleep", new=AsyncMock()),
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"),
        patch("bao.config.onboarding.infer_language", return_value="zh"),
    ):
        await send_startup_greeting(
            fake_agent,
            fake_bus,
            startup_options(config, on_desktop_startup_message=on_desktop),
        )

    fake_agent.provider.chat.assert_awaited_once()
    fake_agent.process_direct.assert_not_awaited()
    fake_bus.publish_outbound.assert_not_awaited()
    on_desktop.assert_awaited_once_with(
        DesktopStartupMessage(
            content="你是想让我帮你设置提醒吗？",
            role="assistant",
            entrance_style="greeting",
        )
    )


@pytest.mark.asyncio
async def test_startup_greeting_uses_explicit_persona_language_tag(tmp_path) -> None:
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

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "INSTRUCTIONS.md").write_text("# INSTRUCTIONS\n", encoding="utf-8")
    (workspace / "PERSONA.md").write_text(
        "# Persona\n- **Language**: Español\n- Style: Friendly\n",
        encoding="utf-8",
    )

    config = make_hub_config(workspace_path=str(workspace))
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
    messages = await_args.args[0].messages
    assert "Respond in Español" in messages[0]["content"]
    assert messages[1]["content"] == '{"event":"system.user_online"}'
