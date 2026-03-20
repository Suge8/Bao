"""Core tests for bao.hub.builder."""

from __future__ import annotations

import asyncio
import dataclasses
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import bao.hub.builder as mod
from bao.hub._builder_prompt import StartupPromptOptions
from bao.hub.builder import HubStack, build_hub_stack
from tests._hub_builder_testkit import (
    FakeCron,
    apply_hub_stack_patches,
    build_stack_options,
    make_fake_data_dir,
    make_hub_config,
    set_channels,
)

pytestmark = pytest.mark.integration


class TestImports:
    def test_imports(self):
        from bao.hub.builder import (  # noqa: F811
            HubStack,  # noqa: F811, F401
            build_hub_stack,  # noqa: F811
            send_startup_greeting,
        )

        assert callable(build_hub_stack)
        assert asyncio.iscoroutinefunction(send_startup_greeting)


class TestGatewayStack:
    def test_has_seven_fields(self):
        fields = [f.name for f in dataclasses.fields(HubStack)]
        assert fields == [
            "config",
            "bus",
            "session_manager",
            "cron",
            "heartbeat",
            "agent",
            "dispatcher",
            "channels",
        ]

    def test_is_dataclass(self):
        assert dataclasses.is_dataclass(HubStack)


@pytest.mark.smoke
def test_startup_system_prompt_keeps_bao_identity() -> None:
    prompt = mod._build_startup_system_prompt(
        StartupPromptOptions(
            persona_text="",
            instructions_text="",
            preferred_language="中文",
            channel="feishu",
            chat_id="ou_123",
        )
    )

    assert "You are Bao. Keep Bao as your user-facing identity." in prompt
    assert "Keep Bao as your user-facing identity." in prompt
    assert "Treat the user line as startup presence signal" in prompt
    assert "Never acknowledge instructions or metadata" in prompt
    assert "Follow PERSONA.md for your self-name" in prompt
    assert "## Runtime (actual host)" in prompt
    assert "Channel: feishu | Chat: ou_123" in prompt


def test_build_hub_stack_does_not_repair_external_family_active_from_desktop() -> None:
    fake_bus = MagicMock()
    fake_agent = MagicMock()
    fake_channels = MagicMock()
    fake_session_manager = MagicMock()

    config = make_hub_config()
    set_channels(config)

    with (
        patch.object(mod, "__name__", mod.__name__),
        patch("bao.agent.loop.AgentLoop", return_value=fake_agent) as agent_loop_cls,
        patch("bao.bus.queue.MessageBus", return_value=fake_bus),
        patch("bao.channels.manager.ChannelManager", return_value=fake_channels),
        patch("bao.config.loader.get_data_dir", return_value=make_fake_data_dir()),
        patch("bao.cron.service.CronService", side_effect=FakeCron),
        patch("bao.heartbeat.service.HeartbeatService", return_value=MagicMock()),
    ):
        build_hub_stack(
            config,
            MagicMock(),
            build_stack_options(session_manager=fake_session_manager),
        )

    _, agent_kwargs = agent_loop_cls.call_args
    assert agent_kwargs["memory_policy"].recent_window == 10
    fake_session_manager.repair_family_active_from_desktop.assert_not_called()


@pytest.mark.smoke
def test_startup_trigger_is_minimal_internal_event() -> None:
    assert mod._build_startup_trigger() == '{"event":"system.user_online"}'


def test_build_hub_stack_forwards_channel_error_callback() -> None:
    fake_bus = MagicMock()
    fake_agent = MagicMock()
    fake_channels = MagicMock()
    fake_on_channel_error = MagicMock()

    config = make_hub_config()
    set_channels(config)

    with (
        patch.object(mod, "__name__", mod.__name__),
        patch("bao.agent.loop.AgentLoop", return_value=fake_agent) as agent_loop_cls,
        patch("bao.bus.queue.MessageBus", return_value=fake_bus),
        patch("bao.channels.manager.ChannelManager", return_value=fake_channels) as channel_manager_cls,
        patch("bao.config.loader.get_data_dir", return_value=make_fake_data_dir()),
        patch("bao.cron.service.CronService", side_effect=FakeCron),
        patch("bao.heartbeat.service.HeartbeatService", return_value=MagicMock()),
        patch("bao.session.manager.SessionManager", return_value=MagicMock()),
    ):
        stack = build_hub_stack(
            config,
            MagicMock(),
            build_stack_options(on_channel_error=fake_on_channel_error),
        )

    assert stack.channels is fake_channels
    _, kwargs = channel_manager_cls.call_args
    assert kwargs["on_channel_error"] is fake_on_channel_error
    _, agent_kwargs = agent_loop_cls.call_args
    assert agent_kwargs["memory_policy"].recent_window == 10


class TestCronCallbackDefensive:
    @pytest.fixture()
    def stub_job(self):
        from bao.cron.types import CronJob, CronPayload

        return CronJob(
            id="test-job",
            name="test",
            payload=CronPayload(message="hello", deliver=False, channel="hub", to=None),
        )

    @pytest.fixture()
    def failing_agent(self):
        agent = MagicMock()
        agent.process_direct = AsyncMock(side_effect=RuntimeError("boom"))
        return agent

    @pytest.mark.asyncio
    async def test_cron_callback_returns_error_string(self, stub_job, failing_agent):
        fake_bus = MagicMock()
        fake_bus.publish_outbound = AsyncMock()
        config = make_hub_config()
        set_channels(config)

        with apply_hub_stack_patches(
            mod,
            fake_agent=failing_agent,
            fake_bus=fake_bus,
            fake_channels=MagicMock(),
        ):
            stack = build_hub_stack(config, MagicMock(), build_stack_options())

        callback = stack.cron.on_job
        assert callback is not None
        result = await callback(stub_job)
        assert isinstance(result, str)
        assert result.startswith("Error: ")
        assert "boom" in result


@pytest.mark.asyncio
async def test_cron_callback_sets_and_resets_cron_context() -> None:
    from bao.agent.tools.cron import CronTool
    from bao.cron.types import CronJob, CronPayload

    fake_agent = MagicMock()
    fake_agent.process_direct = AsyncMock(return_value="ok")
    fake_cron_tool = MagicMock(spec=CronTool)
    fake_cron_tool.set_cron_context.return_value = object()
    fake_agent.tools.get.return_value = fake_cron_tool

    config = make_hub_config()
    set_channels(config)

    with apply_hub_stack_patches(
        mod,
        fake_agent=fake_agent,
        fake_bus=MagicMock(),
        fake_channels=MagicMock(),
    ):
        stack = build_hub_stack(config, MagicMock(), build_stack_options())

    callback = stack.cron.on_job
    assert callback is not None
    job = CronJob(
        id="cron-1",
        name="test",
        payload=CronPayload(message="hello", deliver=False, channel="hub", to=None),
    )
    await callback(job)

    fake_cron_tool.set_cron_context.assert_called_once_with(True)
    fake_cron_tool.reset_cron_context.assert_called_once_with(
        fake_cron_tool.set_cron_context.return_value
    )
