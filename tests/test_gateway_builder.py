"""Tests for bao.gateway.builder — shared gateway stack builder."""

from __future__ import annotations

import asyncio
import dataclasses
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import bao.gateway.builder as mod
from bao.gateway.builder import GatewayStack, build_gateway_stack, send_startup_greeting


class TestImports:
    """Verify the public API is importable."""

    def test_imports(self):
        from bao.gateway.builder import (  # noqa: F811
            GatewayStack,  # noqa: F811, F401
            build_gateway_stack,  # noqa: F811
            send_startup_greeting,
        )

        assert callable(build_gateway_stack)
        assert asyncio.iscoroutinefunction(send_startup_greeting)


class TestGatewayStack:
    """Verify GatewayStack dataclass shape."""

    def test_has_seven_fields(self):
        fields = [f.name for f in dataclasses.fields(GatewayStack)]
        assert fields == [
            "config",
            "bus",
            "session_manager",
            "cron",
            "heartbeat",
            "agent",
            "channels",
        ]

    def test_is_dataclass(self):
        assert dataclasses.is_dataclass(GatewayStack)


class TestCronCallbackDefensive:
    """Cron callback must catch exceptions and return 'Error: ...' string."""

    @pytest.fixture()
    def stub_job(self):
        from bao.cron.types import CronJob, CronPayload

        return CronJob(
            id="test-job",
            name="test",
            payload=CronPayload(
                message="hello",
                deliver=False,
                channel="gateway",
                to=None,
            ),
        )

    @pytest.fixture()
    def failing_agent(self):
        agent = MagicMock()
        agent.process_direct = AsyncMock(side_effect=RuntimeError("boom"))
        return agent

    @pytest.mark.asyncio
    async def test_cron_callback_returns_error_string(self, stub_job, failing_agent):
        """When agent.process_direct raises, callback returns 'Error: ...' instead of crashing."""
        # We need to extract the on_cron_job closure.
        # Build a minimal mock cron service that captures the callback.
        _ = None  # placeholder for callback capture (unused in this test path)

        class FakeCron:
            on_job = None

            def __init__(self, path):
                pass

        # Patch the imports inside build_gateway_stack to use our fakes
        fake_bus = MagicMock()
        fake_bus.publish_outbound = AsyncMock()

        with (
            patch.object(mod, "__name__", mod.__name__),
            patch("bao.agent.loop.AgentLoop", return_value=failing_agent),
            patch("bao.bus.queue.MessageBus", return_value=fake_bus),
            patch("bao.channels.manager.ChannelManager", return_value=MagicMock()),
            patch(
                "bao.config.loader.get_data_dir",
                return_value=MagicMock(
                    __truediv__=lambda s, x: MagicMock(__truediv__=lambda s, x: "/tmp/fake")
                ),
            ),
            patch("bao.cron.service.CronService", side_effect=FakeCron),
            patch("bao.heartbeat.service.HeartbeatService", return_value=MagicMock()),
            patch("bao.session.manager.SessionManager", return_value=MagicMock()),
        ):
            config = MagicMock()
            config.workspace_path = "/tmp/test"
            config.agents.defaults.model = "test"
            config.agents.defaults.temperature = 0.1
            config.agents.defaults.max_tokens = 100
            config.agents.defaults.max_tool_iterations = 5
            config.agents.defaults.memory_window = 10
            config.agents.defaults.models = []
            config.tools.web.search = MagicMock()
            config.tools.exec = MagicMock()
            config.tools.embedding = MagicMock()
            config.tools.restrict_to_workspace = False
            config.tools.mcp_servers = {}

            stack = build_gateway_stack(config, MagicMock())

        # The cron callback is set on the FakeCron instance
        callback = stack.cron.on_job
        assert callback is not None

        result = await callback(stub_job)
        assert isinstance(result, str)
        assert result.startswith("Error: ")
        assert "boom" in result


@pytest.mark.asyncio
async def test_heartbeat_uses_whatsapp_jid_and_skips_discord_allow_from() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()

    fake_agent = MagicMock()
    fake_agent.process_direct = AsyncMock(return_value="ok")

    class FakeCron:
        on_job = None

        def __init__(self, path):
            pass

    class FakeChannels:
        async def stop_all(self):
            return None

    with (
        patch.object(mod, "__name__", mod.__name__),
        patch("bao.agent.loop.AgentLoop", return_value=fake_agent),
        patch("bao.bus.queue.MessageBus", return_value=fake_bus),
        patch("bao.channels.manager.ChannelManager", return_value=FakeChannels()),
        patch(
            "bao.config.loader.get_data_dir",
            return_value=MagicMock(
                __truediv__=lambda s, x: MagicMock(__truediv__=lambda s, y: "/tmp/fake")
            ),
        ),
        patch("bao.cron.service.CronService", side_effect=FakeCron),
        patch("bao.session.manager.SessionManager", return_value=MagicMock()),
    ):
        config = MagicMock()
        config.workspace_path = "/tmp/test"
        config.agents.defaults.model = "test"
        config.agents.defaults.temperature = 0.1
        config.agents.defaults.max_tokens = 100
        config.agents.defaults.max_tool_iterations = 5
        config.agents.defaults.memory_window = 10
        config.agents.defaults.models = []
        config.tools.web.search = MagicMock()
        config.tools.exec = MagicMock()
        config.tools.embedding = MagicMock()
        config.tools.restrict_to_workspace = False
        config.tools.mcp_servers = {}
        config.gateway.heartbeat.interval_s = 60
        config.gateway.heartbeat.enabled = True

        channels = MagicMock()
        channels.telegram.enabled = False
        channels.telegram.allow_from = []
        channels.whatsapp.enabled = True
        channels.whatsapp.allow_from = ["8613800138000"]
        channels.discord.enabled = True
        channels.discord.allow_from = ["discord-user-id"]
        channels.feishu.enabled = False
        channels.feishu.allow_from = []
        channels.dingtalk.enabled = False
        channels.dingtalk.allow_from = []
        channels.qq.enabled = False
        channels.qq.allow_from = []
        channels.imessage.enabled = False
        channels.imessage.allow_from = []
        channels.email.enabled = False
        channels.email.allow_from = []
        config.channels = channels

        stack = build_gateway_stack(config, MagicMock())

    assert stack.heartbeat.on_execute is not None
    assert stack.heartbeat.on_notify is not None

    await stack.heartbeat.on_execute("do tasks")
    fake_agent.process_direct.assert_awaited_once()
    call_kwargs = fake_agent.process_direct.await_args.kwargs
    assert call_kwargs["channel"] == "whatsapp"
    assert call_kwargs["chat_id"] == "8613800138000@s.whatsapp.net"

    await stack.heartbeat.on_notify("notify")
    fake_bus.publish_outbound.assert_awaited_once()
    outbound = fake_bus.publish_outbound.await_args.args[0]
    assert outbound.channel == "whatsapp"
    assert outbound.chat_id == "8613800138000@s.whatsapp.net"


@pytest.mark.asyncio
async def test_heartbeat_skips_telegram_username_target() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()

    fake_agent = MagicMock()
    fake_agent.process_direct = AsyncMock(return_value="ok")

    class FakeCron:
        on_job = None

        def __init__(self, path):
            pass

    class FakeChannels:
        async def stop_all(self):
            return None

    with (
        patch.object(mod, "__name__", mod.__name__),
        patch("bao.agent.loop.AgentLoop", return_value=fake_agent),
        patch("bao.bus.queue.MessageBus", return_value=fake_bus),
        patch("bao.channels.manager.ChannelManager", return_value=FakeChannels()),
        patch(
            "bao.config.loader.get_data_dir",
            return_value=MagicMock(
                __truediv__=lambda s, x: MagicMock(__truediv__=lambda s, y: "/tmp/fake")
            ),
        ),
        patch("bao.cron.service.CronService", side_effect=FakeCron),
        patch("bao.session.manager.SessionManager", return_value=MagicMock()),
    ):
        config = MagicMock()
        config.workspace_path = "/tmp/test"
        config.agents.defaults.model = "test"
        config.agents.defaults.temperature = 0.1
        config.agents.defaults.max_tokens = 100
        config.agents.defaults.max_tool_iterations = 5
        config.agents.defaults.memory_window = 10
        config.agents.defaults.models = []
        config.tools.web.search = MagicMock()
        config.tools.exec = MagicMock()
        config.tools.embedding = MagicMock()
        config.tools.restrict_to_workspace = False
        config.tools.mcp_servers = {}
        config.gateway.heartbeat.interval_s = 60
        config.gateway.heartbeat.enabled = True

        channels = MagicMock()
        channels.telegram.enabled = True
        channels.telegram.allow_from = ["some_username"]
        channels.whatsapp.enabled = False
        channels.whatsapp.allow_from = []
        channels.discord.enabled = False
        channels.discord.allow_from = []
        channels.feishu.enabled = True
        channels.feishu.allow_from = ["ou_123"]
        channels.dingtalk.enabled = False
        channels.dingtalk.allow_from = []
        channels.qq.enabled = False
        channels.qq.allow_from = []
        channels.imessage.enabled = False
        channels.imessage.allow_from = []
        channels.email.enabled = False
        channels.email.allow_from = []
        config.channels = channels

        stack = build_gateway_stack(config, MagicMock())

    assert stack.heartbeat.on_execute is not None

    await stack.heartbeat.on_execute("do tasks")
    fake_agent.process_direct.assert_awaited_once()
    call_kwargs = fake_agent.process_direct.await_args.kwargs
    assert call_kwargs["channel"] == "feishu"
    assert call_kwargs["chat_id"] == "ou_123"


@pytest.mark.asyncio
async def test_heartbeat_accepts_negative_telegram_chat_id() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()

    fake_agent = MagicMock()
    fake_agent.process_direct = AsyncMock(return_value="ok")

    class FakeCron:
        on_job = None

        def __init__(self, path):
            pass

    class FakeChannels:
        async def stop_all(self):
            return None

    with (
        patch.object(mod, "__name__", mod.__name__),
        patch("bao.agent.loop.AgentLoop", return_value=fake_agent),
        patch("bao.bus.queue.MessageBus", return_value=fake_bus),
        patch("bao.channels.manager.ChannelManager", return_value=FakeChannels()),
        patch(
            "bao.config.loader.get_data_dir",
            return_value=MagicMock(
                __truediv__=lambda s, x: MagicMock(__truediv__=lambda s, y: "/tmp/fake")
            ),
        ),
        patch("bao.cron.service.CronService", side_effect=FakeCron),
        patch("bao.session.manager.SessionManager", return_value=MagicMock()),
    ):
        config = MagicMock()
        config.workspace_path = "/tmp/test"
        config.agents.defaults.model = "test"
        config.agents.defaults.temperature = 0.1
        config.agents.defaults.max_tokens = 100
        config.agents.defaults.max_tool_iterations = 5
        config.agents.defaults.memory_window = 10
        config.agents.defaults.models = []
        config.tools.web.search = MagicMock()
        config.tools.exec = MagicMock()
        config.tools.embedding = MagicMock()
        config.tools.restrict_to_workspace = False
        config.tools.mcp_servers = {}
        config.gateway.heartbeat.interval_s = 60
        config.gateway.heartbeat.enabled = True

        channels = MagicMock()
        channels.telegram.enabled = True
        channels.telegram.allow_from = ["-1001234567890"]
        channels.whatsapp.enabled = False
        channels.whatsapp.allow_from = []
        channels.discord.enabled = False
        channels.discord.allow_from = []
        channels.feishu.enabled = True
        channels.feishu.allow_from = ["ou_123"]
        channels.dingtalk.enabled = False
        channels.dingtalk.allow_from = []
        channels.qq.enabled = False
        channels.qq.allow_from = []
        channels.imessage.enabled = False
        channels.imessage.allow_from = []
        channels.email.enabled = False
        channels.email.allow_from = []
        config.channels = channels

        stack = build_gateway_stack(config, MagicMock())

    assert stack.heartbeat.on_execute is not None

    await stack.heartbeat.on_execute("do tasks")
    fake_agent.process_direct.assert_awaited_once()
    call_kwargs = fake_agent.process_direct.await_args.kwargs
    assert call_kwargs["channel"] == "telegram"
    assert call_kwargs["chat_id"] == "-1001234567890"


@pytest.mark.asyncio
async def test_startup_greeting_skips_telegram_username_target() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()

    config = MagicMock()
    config.workspace_path = "/tmp/test"

    channels = MagicMock()
    channels.telegram.enabled = True
    channels.telegram.allow_from = ["some_username"]
    channels.feishu.enabled = True
    channels.feishu.allow_from = ["ou_123"]
    channels.dingtalk.enabled = False
    channels.dingtalk.allow_from = []
    channels.imessage.enabled = False
    channels.imessage.allow_from = []
    channels.qq.enabled = False
    channels.qq.allow_from = []
    channels.email.enabled = False
    channels.email.allow_from = []
    channels.whatsapp.enabled = False
    channels.whatsapp.allow_from = []
    config.channels = channels

    with (
        patch("bao.gateway.builder.asyncio.sleep", new=AsyncMock()),
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="lang_select"),
        patch("bao.config.onboarding.LANG_PICKER", "picker"),
    ):
        await send_startup_greeting(fake_agent, fake_bus, config)

    assert fake_bus.publish_outbound.await_count == 1
    outbound = fake_bus.publish_outbound.await_args.args[0]
    assert outbound.channel == "feishu"
    assert outbound.chat_id == "ou_123"


@pytest.mark.asyncio
async def test_startup_greeting_accepts_negative_telegram_chat_id() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()

    config = MagicMock()
    config.workspace_path = "/tmp/test"

    channels = MagicMock()
    channels.telegram.enabled = True
    channels.telegram.allow_from = ["-1001234567890"]
    channels.feishu.enabled = False
    channels.feishu.allow_from = []
    channels.dingtalk.enabled = False
    channels.dingtalk.allow_from = []
    channels.imessage.enabled = False
    channels.imessage.allow_from = []
    channels.qq.enabled = False
    channels.qq.allow_from = []
    channels.email.enabled = False
    channels.email.allow_from = []
    channels.whatsapp.enabled = False
    channels.whatsapp.allow_from = []
    config.channels = channels

    with (
        patch("bao.gateway.builder.asyncio.sleep", new=AsyncMock()),
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="lang_select"),
        patch("bao.config.onboarding.LANG_PICKER", "picker"),
    ):
        await send_startup_greeting(fake_agent, fake_bus, config)

    assert fake_bus.publish_outbound.await_count == 1
    outbound = fake_bus.publish_outbound.await_args.args[0]
    assert outbound.channel == "telegram"
    assert outbound.chat_id == "-1001234567890"
