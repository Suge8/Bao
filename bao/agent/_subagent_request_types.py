from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bao.agent.run_controller import RunLoopState
from bao.agent.tool_exposure import ToolExposureSnapshot
from bao.bus.queue import MessageBus

if TYPE_CHECKING:
    from bao.agent.artifacts import ArtifactStore


@dataclass(frozen=True)
class SubagentManagerOptions:
    workspace: Path
    bus: MessageBus
    model: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096
    reasoning_effort: str | None = None
    service_tier: str | None = None
    search_config: Any | None = None
    web_proxy: str | None = None
    exec_config: Any | None = None
    restrict_to_workspace: bool = False
    max_iterations: int = 20
    context_management: str = "auto"
    tool_output_offload_chars: int = 8000
    tool_output_preview_chars: int = 3000
    tool_output_hard_chars: int = 6000
    context_compact_bytes_est: int = 240000
    context_compact_keep_recent_tool_blocks: int = 4
    artifact_retention_days: int = 7
    memory_store: Any | None = None
    memory_policy: Any | None = None
    image_generation_config: Any | None = None
    desktop_config: Any | None = None
    browser_enabled: bool = True
    sessions: Any | None = None
    utility_provider: Any | None = None
    utility_model: str | None = None
    experience_mode: str = "utility"


@dataclass(frozen=True)
class SubagentAuxRuntimeConfig:
    utility_provider: Any | None
    utility_model: str | None
    experience_mode: str


@dataclass(frozen=True)
class SpawnRequest:
    task: str
    label: str | None = None
    origin_channel: str = "hub"
    origin_chat_id: str = "direct"
    session_key: str | None = None
    context_from: str | None = None
    child_session_key: str | None = None


@dataclass(frozen=True)
class StatusUpdate:
    task_id: str
    iteration: int | None = None
    phase: str | None = None
    tool_steps: int | None = None
    status: str | None = None
    result_summary: str | None = None
    action: str | None = None


@dataclass(frozen=True)
class DiagnosticRecord:
    stage: str
    message: str
    code: str = ""
    retryable: bool | None = None
    task_id: str = ""
    label: str = ""
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class CodingProgressSetupRequest:
    task_id: str
    tool_call: Any
    coding_tool: Any
    tool_step: int


@dataclass(frozen=True)
class SubagentPromptRequest:
    task: str
    channel: str | None
    has_search: bool = False
    has_browser: bool = False
    coding_tools: list[str] | None = None
    coding_backend_issues: list[str] | None = None
    related_memory: list[str] | None = None
    related_experience: list[str] | None = None


@dataclass(frozen=True)
class PrepareMessagesRequest:
    task_id: str
    task: str
    child_session_key: str | None
    channel: str | None
    has_search: bool
    has_browser: bool
    coding_tools: list[str]
    coding_backend_issues: list[str]
    related_memory: list[str]
    related_experience: list[str]
    context_from: str | None


@dataclass(frozen=True)
class ToolSetupResult:
    tools: Any
    coding_tool: Any
    coding_tools: list[str]
    has_search: bool
    has_browser: bool


@dataclass(frozen=True)
class PreIterationRequest:
    task: str
    messages: list[dict[str, Any]]
    initial_messages: list[dict[str, Any]]
    artifact_store: "ArtifactStore | None"
    tool_trace: list[str]
    sufficiency_trace: list[str]
    reasoning_snippets: list[str]
    failed_directions: list[str]
    state: RunLoopState


@dataclass(frozen=True)
class ToolCallExecutionRequest:
    task_id: str
    tool_call: Any
    tools: Any
    coding_tool: Any
    artifact_store: "ArtifactStore | None"
    messages: list[dict[str, Any]]
    tool_trace: list[str]
    sufficiency_trace: list[str]
    failed_directions: list[str]
    state: RunLoopState


@dataclass(frozen=True)
class ArchiveRunRequest:
    task_id: str
    task: str
    artifact_store: "ArtifactStore | None"
    started_at: str
    finished_at: str
    state: RunLoopState
    tool_trace: list[str]
    tools_used: list[str]
    reasoning_snippets: list[str]
    tool_exposure_history: list[ToolExposureSnapshot]
    provider_finish_reason: str
    exit_reason: str


@dataclass(frozen=True)
class AnnounceResultRequest:
    task_id: str
    label: str
    task: str
    result: str
    origin: dict[str, str]
    status: str


@dataclass(frozen=True)
class FinalizeSuccessRequest:
    task_id: str
    label: str
    task: str
    final_result: str | None
    origin: dict[str, str]
    iteration: int
    tool_step: int


@dataclass(frozen=True)
class FinalizeFailureRequest:
    task_id: str
    label: str
    task: str
    origin: dict[str, str]
    error: Exception


@dataclass(frozen=True)
class RunRequest:
    task_id: str
    task: str
    label: str
    origin: dict[str, str]
    context_from: str | None = None
