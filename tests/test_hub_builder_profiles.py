from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

from bao.hub.builder import BuildHubStackOptions, build_hub_stack
from bao.profile import ProfileContext
from bao.runtime_diagnostics import get_runtime_diagnostics_store


def _make_profile_context() -> ProfileContext:
    return ProfileContext(
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


def _build_hub_config() -> MagicMock:
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
    config.hub.heartbeat.interval_s = 60
    config.hub.heartbeat.enabled = True
    return config


def test_build_hub_stack_uses_profile_context_roots() -> None:
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

    profile_context = _make_profile_context()
    config = _build_hub_config()

    with (
        patch("bao.bus.queue.MessageBus", return_value=fake_bus),
        patch("bao.channels.manager.ChannelManager", return_value=fake_channels),
        patch("bao.cron.service.CronService", side_effect=FakeCron) as cron_cls,
        patch("bao.heartbeat.service.HeartbeatService", return_value=fake_heartbeat) as heartbeat_cls,
        patch("bao.session.manager.SessionManager", return_value=fake_session_manager) as session_cls,
        patch.dict(sys.modules, {"bao.agent.loop": agent_module}),
    ):
        stack = build_hub_stack(
            config,
            MagicMock(),
            BuildHubStackOptions(profile_context=profile_context),
        )

    assert stack.session_manager is fake_session_manager
    session_cls.assert_called_once_with(profile_context.state_root)
    cron_cls.assert_called_once_with(profile_context.cron_store_path)
    heartbeat_args, heartbeat_kwargs = heartbeat_cls.call_args
    assert heartbeat_kwargs == {}
    assert heartbeat_args[0].workspace == profile_context.prompt_root
    _, agent_kwargs = agent_module.AgentLoop.call_args
    assert agent_kwargs["workspace"] == config.workspace_path
    assert agent_kwargs["prompt_root"] == profile_context.prompt_root
    assert agent_kwargs["state_root"] == profile_context.state_root
    assert agent_kwargs["profile_id"] == "work"
    assert agent_kwargs["profile_metadata"]["currentProfileId"] == "work"
    assert agent_kwargs["profile_metadata"]["currentProfileName"] == "Work"
    assert any(item["id"] == "work" and item["isCurrent"] for item in agent_kwargs["profile_metadata"]["profiles"])
    assert agent_kwargs["memory_policy"].recent_window == 10


def test_build_hub_stack_prewarms_route_state(tmp_path) -> None:
    store = get_runtime_diagnostics_store()
    store.clear()
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "hub-route-index.json").write_text(
        '{\n  "desktop:local::s1": "work"\n}\n',
        encoding="utf-8",
    )
    (data_dir / "hub-channel-bindings.json").write_text(
        '{\n  "channel=telegram|peer=-100123": "work"\n}\n',
        encoding="utf-8",
    )

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

    profile_context = _make_profile_context()
    config = _build_hub_config()

    with (
        patch("bao.bus.queue.MessageBus", return_value=fake_bus),
        patch("bao.channels.manager.ChannelManager", return_value=fake_channels),
        patch("bao.config.loader.get_data_dir", return_value=data_dir),
        patch("bao.cron.service.CronService", side_effect=FakeCron),
        patch("bao.heartbeat.service.HeartbeatService", return_value=fake_heartbeat),
        patch("bao.session.manager.SessionManager", return_value=fake_session_manager),
        patch.dict(sys.modules, {"bao.agent.loop": agent_module}),
    ):
        build_hub_stack(
            config,
            MagicMock(),
            BuildHubStackOptions(profile_context=profile_context),
        )

    snapshot = store.snapshot(max_events=4, max_log_lines=0, allowed_sources=("hub_dispatch",))
    assert snapshot["recent_events"][0]["code"] == "hub_route_state_prewarm"
    assert snapshot["recent_events"][0]["details"]["route_entries"] == 1
    assert snapshot["recent_events"][0]["details"]["channel_binding_entries"] == 1
