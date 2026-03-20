from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from bao.agent.run_controller import RunLoopState


@dataclass(slots=True)
class LoopPreIterationRequest:
    messages: list[dict[str, Any]]
    initial_messages: list[dict[str, Any]]
    current_task_ref: asyncio.Task[None] | None
    user_request: str
    artifact_store: Any
    state: RunLoopState
    tool_trace: list[str]
    reasoning_snippets: list[str]
    failed_directions: list[str]
    sufficiency_trace: list[str]
