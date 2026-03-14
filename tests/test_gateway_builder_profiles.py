from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

from bao.gateway.builder import build_gateway_stack
from bao.profile import ProfileContext


def test_build_gateway_stack_uses_profile_context_roots() -> None:
    fake_bus = MagicMock()
    fake_agent = MagicMock()
    fake_channels = MagicMock()
    fake_session_manager = MagicMock()
    fake_heartbeat = MagicMock()
    agent_module = types.ModuleType("bao.agent.loop")
    agent_module.AgentLoop = MagicMock(return_value=fake_agent)

    class FakeCron:
        on_job = None

        def __init__(self, path):
            self.store_path = path

    profile_context = ProfileContext(
        profile_id="work",
        display_name="Work",
        storage_key="work",
        shared_workspace_path=Path("/tmp/shared-workspace"),
        profile_root=Path("/tmp/.bao/profiles/work"),
        prompt_root=Path("/tmp/.bao/profiles/work/prompt"),
        state_root=Path("/tmp/.bao/profiles/work/state"),
        cron_store_path=Path("/tmp/.bao/profiles/work/cron/jobs.json"),
        heartbeat_file=Path("/tmp/.bao/profiles/work/prompt/HEARTBEAT.md"),
    )

    with (
        patch("bao.bus.queue.MessageBus", return_value=fake_bus),
        patch("bao.channels.manager.ChannelManager", return_value=fake_channels),
        patch("bao.cron.service.CronService", side_effect=FakeCron) as cron_cls,
        patch("bao.heartbeat.service.HeartbeatService", return_value=fake_heartbeat) as heartbeat_cls,
        patch("bao.session.manager.SessionManager", return_value=fake_session_manager) as session_cls,
        patch.dict(sys.modules, {"bao.agent.loop": agent_module}),
    ):
        config = MagicMock()
        config.workspace_path = Path("/tmp/shared-workspace")
        config.agents.defaults.model = "test"
        config.agents.defaults.temperature = 0.1
        config.agents.defaults.max_tokens = 100
        config.agents.defaults.max_tool_iterations = 5
        config.agents.defaults.memory_window = 10
        config.agents.defaults.reasoning_effort = None
        config.agents.defaults.service_tier = None
        config.agents.defaults.models = []
        config.tools.web.search = MagicMock()
        config.tools.web.proxy = None
        config.tools.exec = MagicMock()
        config.tools.embedding = MagicMock()
        config.tools.restrict_to_workspace = False
        config.tools.mcp_servers = {}
        config.gateway.heartbeat.interval_s = 60
        config.gateway.heartbeat.enabled = True

        stack = build_gateway_stack(config, MagicMock(), profile_context=profile_context)

    assert stack.session_manager is fake_session_manager
    session_cls.assert_called_once_with(profile_context.state_root)
    cron_cls.assert_called_once_with(profile_context.cron_store_path)
    _, heartbeat_kwargs = heartbeat_cls.call_args
    assert heartbeat_kwargs["workspace"] == profile_context.prompt_root
    _, agent_kwargs = agent_module.AgentLoop.call_args
    assert agent_kwargs["workspace"] == config.workspace_path
    assert agent_kwargs["prompt_root"] == profile_context.prompt_root
    assert agent_kwargs["state_root"] == profile_context.state_root
    assert agent_kwargs["profile_id"] == "work"
    assert agent_kwargs["profile_metadata"]["currentProfileId"] == "work"
    assert agent_kwargs["profile_metadata"]["currentProfileName"] == "Work"
    assert any(item["id"] == "work" and item["isCurrent"] for item in agent_kwargs["profile_metadata"]["profiles"])
    assert agent_kwargs["memory_policy"].recent_window == 10
