from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bao.agent.memory import MemoryPolicy


@dataclass(slots=True)
class LoopInitOptions:
    prompt_root: Any = None
    state_root: Any = None
    profile_id: str | None = None
    profile_metadata: dict[str, Any] | None = None
    model: str | None = None
    max_iterations: int = 20
    temperature: float = 0.7
    max_tokens: int = 4096
    memory_window: int | None = None
    memory_policy: MemoryPolicy | None = None
    reasoning_effort: str | None = None
    service_tier: str | None = None
    search_config: Any = None
    web_proxy: str | None = None
    exec_config: Any = None
    cron_service: Any = None
    embedding_config: Any = None
    restrict_to_workspace: bool = False
    session_manager: Any = None
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    available_models: list[str] = field(default_factory=list)
    config: Any = None
