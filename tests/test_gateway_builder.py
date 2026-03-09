"""Tests for bao.gateway.builder — shared gateway stack builder."""

from __future__ import annotations

import asyncio
import dataclasses
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import bao.gateway.builder as mod
from bao.gateway.builder import (
    DesktopStartupMessage,
    GatewayStack,
    build_gateway_stack,
    send_startup_greeting,
)

pytestmark = pytest.mark.integration


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


@pytest.mark.smoke
def test_startup_system_prompt_keeps_bao_identity() -> None:
    prompt = mod._build_startup_system_prompt(
        persona_text="",
        instructions_text="",
        preferred_language="中文",
        channel="feishu",
        chat_id="ou_123",
    )

    assert "You are Bao. Keep Bao as your user-facing identity." in prompt
    assert "Keep Bao as your user-facing identity." in prompt
    assert "Treat the user line as startup presence signal" in prompt
    assert "Never acknowledge instructions or metadata" in prompt
    assert "Follow PERSONA.md for your self-name" in prompt
    assert "## Runtime (actual host)" in prompt
    assert "Channel: feishu | Chat: ou_123" in prompt


def test_build_gateway_stack_does_not_repair_external_family_active_from_desktop() -> None:
    fake_bus = MagicMock()
    fake_agent = MagicMock()
    fake_channels = MagicMock()
    fake_session_manager = MagicMock()

    class FakeCron:
        on_job = None

        def __init__(self, path):
            pass

    with (
        patch.object(mod, "__name__", mod.__name__),
        patch("bao.agent.loop.AgentLoop", return_value=fake_agent),
        patch("bao.bus.queue.MessageBus", return_value=fake_bus),
        patch("bao.channels.manager.ChannelManager", return_value=fake_channels),
        patch(
            "bao.config.loader.get_data_dir",
            return_value=MagicMock(
                __truediv__=lambda s, x: MagicMock(__truediv__=lambda s, y: "/tmp/fake")
            ),
        ),
        patch("bao.cron.service.CronService", side_effect=FakeCron),
        patch("bao.heartbeat.service.HeartbeatService", return_value=MagicMock()),
    ):
        config = MagicMock()
        config.workspace_path = "/tmp/test"
        config.agents.defaults.model = "test"
        config.agents.defaults.temperature = 0.1
        config.agents.defaults.max_tokens = 100
        config.agents.defaults.max_tool_iterations = 5
        config.agents.defaults.memory_window = 10
        config.agents.defaults.reasoning_effort = None
        config.agents.defaults.models = []
        config.tools.web.search = MagicMock()
        config.tools.exec = MagicMock()
        config.tools.embedding = MagicMock()
        config.tools.restrict_to_workspace = False
        config.tools.mcp_servers = {}
        config.gateway.heartbeat.interval_s = 60
        config.gateway.heartbeat.enabled = True

        build_gateway_stack(config, MagicMock(), fake_session_manager)

    fake_session_manager.repair_family_active_from_desktop.assert_not_called()


@pytest.mark.smoke
def test_startup_trigger_is_minimal_internal_event() -> None:
    assert mod._build_startup_trigger() == '{"event":"system.user_online"}'


def test_build_gateway_stack_forwards_channel_error_callback() -> None:
    fake_bus = MagicMock()
    fake_agent = MagicMock()
    fake_channels = MagicMock()
    fake_on_channel_error = MagicMock()

    class FakeCron:
        on_job = None

        def __init__(self, path):
            pass

    with (
        patch.object(mod, "__name__", mod.__name__),
        patch("bao.agent.loop.AgentLoop", return_value=fake_agent),
        patch("bao.bus.queue.MessageBus", return_value=fake_bus),
        patch(
            "bao.channels.manager.ChannelManager", return_value=fake_channels
        ) as channel_manager_cls,
        patch(
            "bao.config.loader.get_data_dir",
            return_value=MagicMock(
                __truediv__=lambda s, x: MagicMock(__truediv__=lambda s, y: "/tmp/fake")
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
        config.agents.defaults.reasoning_effort = None
        config.agents.defaults.models = []
        config.tools.web.search = MagicMock()
        config.tools.exec = MagicMock()
        config.tools.embedding = MagicMock()
        config.tools.restrict_to_workspace = False
        config.tools.mcp_servers = {}
        config.gateway.heartbeat.interval_s = 60
        config.gateway.heartbeat.enabled = True

        stack = build_gateway_stack(config, MagicMock(), on_channel_error=fake_on_channel_error)

    assert stack.channels is fake_channels
    _, kwargs = channel_manager_cls.call_args
    assert kwargs["on_channel_error"] is fake_on_channel_error


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
async def test_heartbeat_uses_later_valid_target_from_shared_target_list() -> None:
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
        channels.telegram.allow_from = ["some_username", "-1001234567890"]
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
    assert stack.heartbeat.on_notify is not None

    await stack.heartbeat.on_execute("do tasks")
    fake_agent.process_direct.assert_awaited_once()
    call_kwargs = fake_agent.process_direct.await_args.kwargs
    assert call_kwargs["channel"] == "telegram"
    assert call_kwargs["chat_id"] == "-1001234567890"

    await stack.heartbeat.on_notify("notify")
    fake_bus.publish_outbound.assert_awaited_once()
    outbound = fake_bus.publish_outbound.await_args.args[0]
    assert outbound.channel == "telegram"
    assert outbound.chat_id == "-1001234567890"


@pytest.mark.asyncio
async def test_heartbeat_without_primary_proactive_target_falls_back_to_cli_and_skips_notify() -> (
    None
):
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
    assert call_kwargs["channel"] == "cli"
    assert call_kwargs["chat_id"] == "direct"

    await stack.heartbeat.on_notify("notify")
    fake_bus.publish_outbound.assert_not_awaited()


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
async def test_heartbeat_accepts_telegram_composite_target() -> None:
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
        channels.telegram.allow_from = ["abc45879|6374137703"]
        channels.whatsapp.enabled = False
        channels.whatsapp.allow_from = []
        channels.discord.enabled = False
        channels.discord.allow_from = []
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
    await stack.heartbeat.on_execute("do tasks")
    fake_agent.process_direct.assert_awaited_once()
    call_kwargs = fake_agent.process_direct.await_args.kwargs
    assert call_kwargs["channel"] == "telegram"
    assert call_kwargs["chat_id"] == "6374137703"


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


@pytest.mark.asyncio
async def test_startup_greeting_accepts_telegram_composite_target() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()

    config = MagicMock()
    config.workspace_path = "/tmp/test"

    channels = MagicMock()
    channels.telegram.enabled = True
    channels.telegram.allow_from = ["abc45879|6374137703"]
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

    config = MagicMock()
    config.workspace_path = "/tmp/test"

    channels = MagicMock()
    channels.telegram.enabled = False
    channels.telegram.allow_from = []
    channels.feishu.enabled = False
    channels.feishu.allow_from = []
    channels.dingtalk.enabled = False
    channels.dingtalk.allow_from = []
    channels.imessage.enabled = True
    channels.imessage.allow_from = ["13800138000"]
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
        run_task = asyncio.create_task(
            send_startup_greeting(
                fake_agent,
                fake_bus,
                config,
                on_desktop_startup_message=on_desktop,
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

    class FakeChannels:
        async def wait_started(self) -> None:
            return None

        async def wait_ready(self, _name: str) -> None:
            await ready_evt.wait()

        async def send_outbound(self, msg) -> None:
            sent.append(msg)

    fake_agent = MagicMock()
    config = MagicMock()
    config.workspace_path = "/tmp/test"

    channels = MagicMock()
    channels.telegram.enabled = False
    channels.telegram.allow_from = []
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
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="lang_select"),
        patch("bao.config.onboarding.LANG_PICKER", "picker"),
    ):
        task = asyncio.create_task(
            send_startup_greeting(fake_agent, fake_bus, config, channels=FakeChannels())
        )
        await asyncio.sleep(0)
        assert fake_bus.publish_outbound.await_count == 0
        assert sent == []
        ready_evt.set()
        await asyncio.wait_for(task, timeout=0.5)

    assert fake_bus.publish_outbound.await_count == 0
    assert len(sent) == 1


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

    config = MagicMock()
    config.workspace_path = "/tmp/test"

    channels = MagicMock()
    channels.telegram.enabled = False
    channels.telegram.allow_from = []
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
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"),
    ):
        await send_startup_greeting(fake_agent, fake_bus, config)

    fake_agent.provider.chat.assert_awaited_once()
    await_args = fake_agent.provider.chat.await_args
    assert await_args is not None
    assert await_args.kwargs["temperature"] == 0.7
    messages = await_args.kwargs["messages"]
    assert "Respond in 中文" in messages[0]["content"]
    assert messages[1]["content"] == '{"event":"system.user_online"}'
    assert "## Runtime (actual host)" in messages[0]["content"]
    assert "Channel: feishu | Chat: ou_123" in messages[0]["content"]
    fake_agent.process_direct.assert_not_awaited()
    assert fake_bus.publish_outbound.await_count == 1
    outbound = fake_bus.publish_outbound.await_args.args[0]
    assert outbound.channel == "feishu"
    assert outbound.chat_id == "ou_123"


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

    config = MagicMock()
    config.workspace_path = "/tmp/test"

    channels = MagicMock()
    channels.telegram.enabled = False
    channels.telegram.allow_from = []
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
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"),
    ):
        await send_startup_greeting(fake_agent, fake_bus, config)

    utility_provider.chat.assert_awaited_once()
    main_provider.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_greeting_desktop_not_blocked_by_external_publish() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()

    fake_agent = MagicMock()
    fake_agent.model = "right-gpt/gpt-5.3-codex"
    fake_agent.provider = MagicMock()
    fake_agent.provider.chat = AsyncMock(return_value=MagicMock(content="unused"))
    fake_agent.process_direct = AsyncMock(return_value="fallback")

    desktop_called = asyncio.Event()

    async def _on_desktop(_content: str) -> None:
        desktop_called.set()

    on_desktop = AsyncMock(side_effect=_on_desktop)

    publish_started = asyncio.Event()
    release_publish = asyncio.Event()

    class FakeRuntimeChannels:
        async def wait_started(self) -> None:
            return None

        async def wait_ready(self, _name: str) -> None:
            return None

        async def send_outbound(self, _msg) -> None:
            publish_started.set()
            await release_publish.wait()

    config = MagicMock()
    config.workspace_path = "/tmp/test"

    channels = MagicMock()
    channels.telegram.enabled = False
    channels.telegram.allow_from = []
    channels.feishu.enabled = False
    channels.feishu.allow_from = []
    channels.dingtalk.enabled = False
    channels.dingtalk.allow_from = []
    channels.imessage.enabled = True
    channels.imessage.allow_from = ["13800138000"]
    channels.qq.enabled = False
    channels.qq.allow_from = []
    channels.email.enabled = False
    channels.email.allow_from = []
    channels.whatsapp.enabled = False
    channels.whatsapp.allow_from = []
    config.channels = channels

    async def _fake_generate(
        _agent,
        _logger,
        *,
        system_prompt: str,
        prompt: str,
        channel: str,
        chat_id: str,
    ) -> str:
        assert system_prompt
        assert prompt
        assert chat_id
        return "desktop-hi" if channel == "desktop" else "imessage-hi"

    with (
        patch("bao.gateway.builder.asyncio.sleep", new=AsyncMock()),
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"),
        patch("bao.gateway.builder._generate_startup_greeting", new=_fake_generate),
    ):
        run_task = asyncio.create_task(
            send_startup_greeting(
                fake_agent,
                fake_bus,
                config,
                on_desktop_startup_message=on_desktop,
                channels=FakeRuntimeChannels(),
            )
        )

        await publish_started.wait()
        await asyncio.wait_for(desktop_called.wait(), timeout=0.5)
        release_publish.set()
        await run_task

    on_desktop.assert_awaited_once_with(
        DesktopStartupMessage(
            content="desktop-hi",
            role="assistant",
            entrance_style="greeting",
        )
    )
    assert fake_bus.publish_outbound.await_count == 0


@pytest.mark.asyncio
async def test_startup_greeting_persists_external_ready_message_to_active_family_session() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()

    fake_agent = MagicMock()
    fake_agent.model = "right-gpt/gpt-5.3-codex"
    fake_agent.max_tokens = 4096
    fake_agent.temperature = 0.1
    fake_agent.provider = MagicMock()
    fake_agent.provider.chat = AsyncMock(return_value=MagicMock(content="hello"))

    class StubSession:
        def __init__(self, key: str) -> None:
            self.key = key
            self.messages: list[dict[str, object]] = []

        def add_message(self, role: str, content: str, **kwargs: object) -> None:
            self.messages.append({"role": role, "content": content, **kwargs})

    session = StubSession("feishu:ou_123::s7")
    session_manager = MagicMock()
    session_manager.get_or_create.return_value = session
    session_manager.resolve_active_session_key.return_value = "feishu:ou_123::s7"

    class FakeRuntimeChannels:
        async def wait_started(self) -> None:
            return None

        async def wait_ready(self, _name: str) -> None:
            return None

        async def send_outbound(self, _msg) -> None:
            return None

    config = MagicMock()
    config.workspace_path = "/tmp/test"

    channels = MagicMock()
    channels.telegram.enabled = False
    channels.telegram.allow_from = []
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

    with patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"):
        await send_startup_greeting(
            fake_agent,
            fake_bus,
            config,
            channels=FakeRuntimeChannels(),
            session_manager=session_manager,
        )

    fake_bus.publish_outbound.assert_not_awaited()
    session_manager.get_or_create.assert_called_once_with("feishu:ou_123::s7")
    session_manager.save.assert_called_once_with(session)
    session_manager.mark_desktop_seen_ai_if_active.assert_called_once_with("feishu:ou_123::s7")
    assert session.messages == [
        {
            "role": "assistant",
            "content": "hello",
            "status": "done",
            "format": "markdown",
            "entrance_style": "greeting",
        }
    ]


@pytest.mark.asyncio
async def test_startup_onboarding_persists_external_message_to_session_manager() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()

    class StubSession:
        def __init__(self, key: str) -> None:
            self.key = key
            self.messages: list[dict[str, object]] = []

        def add_message(self, role: str, content: str, **kwargs: object) -> None:
            self.messages.append({"role": role, "content": content, **kwargs})

    session = StubSession("imessage:13800138000")
    session_manager = MagicMock()
    session_manager.get_or_create.return_value = session
    session_manager.resolve_active_session_key.return_value = "imessage:13800138000"

    class FakeRuntimeChannels:
        async def wait_started(self) -> None:
            return None

        async def wait_ready(self, _name: str) -> None:
            return None

        async def send_outbound(self, _msg) -> None:
            return None

    config = MagicMock()
    config.workspace_path = "/tmp/test"

    channels = MagicMock()
    channels.telegram.enabled = False
    channels.telegram.allow_from = []
    channels.feishu.enabled = False
    channels.feishu.allow_from = []
    channels.dingtalk.enabled = False
    channels.dingtalk.allow_from = []
    channels.imessage.enabled = True
    channels.imessage.allow_from = ["13800138000"]
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
        await send_startup_greeting(
            MagicMock(),
            fake_bus,
            config,
            channels=FakeRuntimeChannels(),
            session_manager=session_manager,
        )

    fake_bus.publish_outbound.assert_not_awaited()
    session_manager.get_or_create.assert_called_once_with("imessage:13800138000")
    session_manager.save.assert_called_once_with(session)
    session_manager.mark_desktop_seen_ai_if_active.assert_called_once_with("imessage:13800138000")
    assert session.messages == [
        {
            "role": "assistant",
            "content": "picker",
            "status": "done",
            "format": "markdown",
            "entrance_style": "assistantReceived",
        }
    ]


@pytest.mark.asyncio
async def test_startup_greeting_does_not_persist_external_message_when_send_fails() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()

    fake_agent = MagicMock()
    fake_agent.model = "right-gpt/gpt-5.3-codex"
    fake_agent.provider = MagicMock()
    fake_agent.provider.chat = AsyncMock(return_value=MagicMock(content="hello"))

    class FakeRuntimeChannels:
        async def wait_started(self) -> None:
            return None

        async def wait_ready(self, _name: str) -> None:
            return None

        async def send_outbound(self, _msg) -> None:
            raise RuntimeError("send denied")

    session_manager = MagicMock()
    config = MagicMock()
    config.workspace_path = "/tmp/test"

    channels = MagicMock()
    channels.telegram.enabled = False
    channels.telegram.allow_from = []
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

    with patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"):
        await send_startup_greeting(
            fake_agent,
            fake_bus,
            config,
            channels=FakeRuntimeChannels(),
            session_manager=session_manager,
        )

    fake_bus.publish_outbound.assert_not_awaited()
    session_manager.get_or_create.assert_not_called()
    session_manager.save.assert_not_called()


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

    config = MagicMock()
    config.workspace_path = "/tmp/test"

    channels = MagicMock()
    channels.telegram.enabled = False
    channels.telegram.allow_from = []
    channels.feishu.enabled = False
    channels.feishu.allow_from = []
    channels.dingtalk.enabled = False
    channels.dingtalk.allow_from = []
    channels.imessage.enabled = True
    channels.imessage.allow_from = ["13800138000"]
    channels.qq.enabled = False
    channels.qq.allow_from = []
    channels.email.enabled = False
    channels.email.allow_from = []
    channels.whatsapp.enabled = False
    channels.whatsapp.allow_from = []
    config.channels = channels

    async def _fake_generate(
        _agent,
        _logger,
        *,
        system_prompt: str,
        prompt: str,
        channel: str,
        chat_id: str,
    ) -> str:
        assert system_prompt
        assert prompt
        assert chat_id
        return "desktop-hi" if channel == "desktop" else "imessage-hi"

    with (
        patch("bao.gateway.builder.asyncio.sleep", new=AsyncMock()),
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"),
        patch("bao.gateway.builder._generate_startup_greeting", new=_fake_generate),
    ):
        run_task = asyncio.create_task(
            send_startup_greeting(
                fake_agent,
                fake_bus,
                config,
                on_desktop_startup_message=on_desktop,
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

    config = MagicMock()
    config.workspace_path = "/tmp/test"

    channels = MagicMock()
    channels.telegram.enabled = True
    channels.telegram.allow_from = ["-1001234567890"]
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
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"),
    ):
        await send_startup_greeting(fake_agent, fake_bus, config)

    assert fake_agent.provider.chat.await_count == 2
    fake_agent.process_direct.assert_not_awaited()
    assert fake_bus.publish_outbound.await_count == 2
    outbound = fake_bus.publish_outbound.await_args.args[0]
    assert outbound.channel == "feishu"
    assert outbound.chat_id == "ou_123"


@pytest.mark.asyncio
async def test_startup_greeting_provider_failure_falls_back_to_prompt() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()
    fake_agent.model = "right-gpt/gpt-5.3-codex"
    fake_agent.max_tokens = 4096
    fake_agent.temperature = 0.1
    fake_agent.provider = MagicMock()
    fake_agent.provider.chat = AsyncMock(side_effect=RuntimeError("provider down"))
    fake_agent.process_direct = AsyncMock(return_value="should-not-be-used")

    config = MagicMock()
    config.workspace_path = "/tmp/test"

    channels = MagicMock()
    channels.telegram.enabled = False
    channels.telegram.allow_from = []
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
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"),
    ):
        await send_startup_greeting(fake_agent, fake_bus, config)

    fake_agent.provider.chat.assert_awaited_once()
    fake_agent.process_direct.assert_not_awaited()
    assert fake_bus.publish_outbound.await_count == 1
    outbound = fake_bus.publish_outbound.await_args.args[0]
    assert outbound.channel == "feishu"
    assert outbound.chat_id == "ou_123"
    assert outbound.content == '{"event":"system.user_online"}'


@pytest.mark.asyncio
async def test_startup_greeting_keeps_model_output_without_audit() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()
    fake_agent.model = "right-gpt/gpt-5.3-codex"
    fake_agent.max_tokens = 4096
    fake_agent.temperature = 0.1
    fake_agent.provider = MagicMock()
    fake_agent.provider.chat = AsyncMock(
        return_value=MagicMock(content="你是想让我帮你设置提醒吗？")
    )
    fake_agent.process_direct = AsyncMock(return_value="should-not-be-used")

    config = MagicMock()
    config.workspace_path = "/tmp/test"

    channels = MagicMock()
    channels.telegram.enabled = False
    channels.telegram.allow_from = []
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
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"),
        patch("bao.config.onboarding.infer_language", return_value="zh"),
    ):
        await send_startup_greeting(fake_agent, fake_bus, config)

    fake_agent.provider.chat.assert_awaited_once()
    fake_agent.process_direct.assert_not_awaited()
    assert fake_bus.publish_outbound.await_count == 1
    outbound = fake_bus.publish_outbound.await_args.args[0]
    assert outbound.channel == "feishu"
    assert outbound.chat_id == "ou_123"
    assert outbound.content == "你是想让我帮你设置提醒吗？"


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

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "INSTRUCTIONS.md").write_text("# INSTRUCTIONS\n", encoding="utf-8")
    (workspace / "PERSONA.md").write_text(
        "# Persona\n- **Language**: Español\n- Style: Friendly\n",
        encoding="utf-8",
    )

    config = MagicMock()
    config.workspace_path = str(workspace)

    channels = MagicMock()
    channels.telegram.enabled = False
    channels.telegram.allow_from = []
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
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"),
    ):
        await send_startup_greeting(fake_agent, fake_bus, config)

    fake_agent.provider.chat.assert_awaited_once()
    await_args = fake_agent.provider.chat.await_args
    assert await_args is not None
    messages = await_args.kwargs["messages"]
    assert "Respond in Español" in messages[0]["content"]
    assert messages[1]["content"] == '{"event":"system.user_online"}'
