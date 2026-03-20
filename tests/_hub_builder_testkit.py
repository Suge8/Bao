from __future__ import annotations

from collections.abc import Iterable
from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

from bao.hub.builder import BuildHubStackOptions, StartupGreetingOptions


class FakeCron:
    on_job = None

    def __init__(self, _path):
        pass


class FakeLifecycleChannels:
    async def stop_all(self):
        return None


CHANNEL_NAMES = (
    "telegram",
    "feishu",
    "dingtalk",
    "imessage",
    "qq",
    "email",
    "whatsapp",
    "discord",
)
PATCH_OPTION_DEFAULTS = {
    "fake_heartbeat": None,
    "fake_session_manager": None,
    "patch_heartbeat": True,
}
STARTUP_OPTION_DEFAULTS = {
    "on_desktop_startup_message": None,
    "on_startup_activity": None,
    "channels": None,
    "session_manager": None,
    "profile_context": None,
}


def make_fake_data_dir() -> MagicMock:
    return MagicMock(__truediv__=lambda _s, _x: MagicMock(__truediv__=lambda _s, _y: "/tmp/fake"))


def make_hub_config(*, workspace_path: str = "/tmp/test") -> MagicMock:
    config = MagicMock()
    config.workspace_path = workspace_path
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


def _ensure_known_keys(values: dict[str, object], allowed_keys: tuple[str, ...]) -> None:
    extra_keys = sorted(set(values).difference(allowed_keys))
    if extra_keys:
        raise TypeError(f"Unsupported keys: {', '.join(extra_keys)}")


def _resolve_channel_targets(channel_targets: dict[str, Iterable[str]]) -> dict[str, Iterable[str]]:
    _ensure_known_keys(channel_targets, CHANNEL_NAMES)
    return {name: channel_targets.get(name, ()) for name in CHANNEL_NAMES}


def _resolve_option_values(
    overrides: dict[str, object],
    defaults: dict[str, object],
) -> dict[str, object]:
    _ensure_known_keys(overrides, tuple(defaults))
    return {**defaults, **overrides}


def set_channels(config: MagicMock, **channel_targets: Iterable[str]) -> MagicMock:
    channels = MagicMock()
    for name, allow_from in _resolve_channel_targets(channel_targets).items():
        _set_channel(channels, name, allow_from)
    config.channels = channels
    return channels


def _set_channel(channels: MagicMock, name: str, allow_from: Iterable[str]) -> None:
    values = list(allow_from)
    channel = getattr(channels, name)
    channel.enabled = bool(values)
    channel.allow_from = values


def hub_stack_patchers(
    mod,
    *,
    fake_agent: MagicMock,
    fake_bus: MagicMock,
    fake_channels: object,
    **overrides: object,
):
    option_values = _resolve_option_values(overrides, PATCH_OPTION_DEFAULTS)
    patchers = [
        patch.object(mod, "__name__", mod.__name__),
        patch("bao.agent.loop.AgentLoop", return_value=fake_agent),
        patch("bao.bus.queue.MessageBus", return_value=fake_bus),
        patch("bao.channels.manager.ChannelManager", return_value=fake_channels),
        patch("bao.config.loader.get_data_dir", return_value=make_fake_data_dir()),
        patch("bao.cron.service.CronService", side_effect=FakeCron),
        patch(
            "bao.session.manager.SessionManager",
            return_value=option_values["fake_session_manager"] or MagicMock(),
        ),
    ]
    if option_values["patch_heartbeat"]:
        patchers.append(
            patch(
                "bao.heartbeat.service.HeartbeatService",
                return_value=option_values["fake_heartbeat"] or MagicMock(),
            )
        )
    return tuple(patchers)


@contextmanager
def apply_hub_stack_patches(
    mod,
    *,
    fake_agent: MagicMock,
    fake_bus: MagicMock,
    fake_channels: object,
    **overrides: object,
):
    with ExitStack() as stack:
        for patcher in hub_stack_patchers(
            mod,
            fake_agent=fake_agent,
            fake_bus=fake_bus,
            fake_channels=fake_channels,
            **overrides,
        ):
            stack.enter_context(patcher)
        yield


def build_stack_options(
    *,
    session_manager: object | None = None,
    on_channel_error: object | None = None,
    profile_context: object | None = None,
) -> BuildHubStackOptions:
    return BuildHubStackOptions(
        session_manager=session_manager,
        on_channel_error=on_channel_error,
        profile_context=profile_context,
    )


def startup_options(config: MagicMock, **overrides: object) -> StartupGreetingOptions:
    option_values = _resolve_option_values(overrides, STARTUP_OPTION_DEFAULTS)
    return StartupGreetingOptions(
        config=config,
        on_desktop_startup_message=option_values["on_desktop_startup_message"],
        on_startup_activity=option_values["on_startup_activity"],
        channels=option_values["channels"],
        session_manager=option_values["session_manager"],
        profile_context=option_values["profile_context"],
    )
