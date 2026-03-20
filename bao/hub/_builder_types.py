from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bao.profile import ProfileContext


@dataclass
class HubStack:
    config: Any
    bus: Any
    session_manager: Any
    cron: Any
    heartbeat: Any
    agent: Any
    dispatcher: Any
    channels: Any


@dataclass(frozen=True)
class DesktopStartupMessage:
    content: str
    role: str
    entrance_style: str = "none"


@dataclass(frozen=True)
class BuildHubStackOptions:
    session_manager: Any | None = None
    on_channel_error: Callable[[str, str, str], None] | None = None
    profile_context: ProfileContext | None = None


@dataclass(frozen=True)
class StartupGreetingOptions:
    config: Any
    on_desktop_startup_message: Any | None = None
    on_startup_activity: Any | None = None
    channels: Any | None = None
    session_manager: Any | None = None
    profile_context: ProfileContext | None = None
