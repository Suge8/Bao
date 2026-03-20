from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from bao.agent._loop_types import ToolObservabilityCounters
from bao.agent.protocol import StreamEvent
from bao.agent.run_controller import RunLoopState
from bao.agent.tool_exposure import ToolExposureSnapshot


@dataclass(slots=True)
class RunAgentLoopOptions:
    on_progress: Callable[[str], Awaitable[None]] | None = None
    on_tool_hint: Callable[[str], Awaitable[None]] | None = None
    artifact_session_key: str | None = None
    return_interrupt: bool = False
    tool_signal_text: str | None = None
    on_event: Callable[[StreamEvent], Awaitable[None]] | None = None
    on_visible_assistant_turn: Callable[[str], Awaitable[None]] | None = None
    tool_hint_lang: str | None = None


@dataclass(slots=True)
class FinalizeToolObservabilityRequest:
    tool_budget: dict[str, int]
    counters: ToolObservabilityCounters
    tools_used: list[str]
    total_errors: int
    last_tool_exposure: ToolExposureSnapshot | None = None


@dataclass(slots=True)
class ArchiveRunArtifactRequest:
    artifact_store: Any
    artifact_session_key: str | None
    started_at: str
    user_request: str
    tool_signal_text: str | None
    state: RunLoopState
    tools_used: list[str]
    tool_trace: list[str]
    reasoning_snippets: list[str]
    tool_exposure_history: list[ToolExposureSnapshot]
    provider_finish_reason: str


@dataclass(slots=True)
class RunLoopContext:
    messages: list[dict[str, Any]]
    state: RunLoopState
    tools_used: list[str]
    tool_trace: list[str]
    reasoning_snippets: list[str]
    completed_tool_msgs: list[dict[str, Any]]
    reply_attachments: list[dict[str, Any]]
    failed_directions: list[str]
    sufficiency_trace: list[str]
    current_task_ref: Any
    started_at: str
    user_request: str
    artifact_store: Any
    tool_budget: dict[str, int]
    counters: ToolObservabilityCounters
    tool_exposure_history: list[ToolExposureSnapshot] = field(default_factory=list)
    last_tool_exposure: ToolExposureSnapshot | None = None
    provider_finish_reason: str = ""
