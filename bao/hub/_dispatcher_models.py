from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class HubRuntimeBundle:
    profile_id: str
    agent: Any
    session_manager: Any


@dataclass(frozen=True, slots=True)
class HubAutomationBundle:
    profile_id: str
    cron: Any
    heartbeat: Any
