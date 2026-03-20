from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bao.agent.tools.registry import ToolRegistry


@dataclass(slots=True)
class MCPToolWrapperSpec:
    server_name: str
    tool_def: Any
    timeout: int = 30
    slim_schema: bool = True
    name_override: str | None = None


@dataclass(slots=True)
class BuildPendingWrappersRequest:
    session: Any
    server_name: str
    tool_defs: list[Any]
    registry: ToolRegistry
    total_registered: int
    max_tools: int
    server_max_tools: int | None
    tool_timeout: int
    server_slim_schema: bool


@dataclass(slots=True)
class RegisterPendingWrappersRequest:
    pending_wrappers: list[Any]
    registry: ToolRegistry
    total_registered: int
    max_tools: int
    server_max_tools: int | None
    server_name: str
