"""Subagent manager for background task execution with progress tracking."""

from __future__ import annotations

from bao.agent.memory import DEFAULT_MEMORY_POLICY
from bao.providers.base import LLMProvider
from bao.runtime_diagnostics import get_runtime_diagnostics_store

from ._subagent_coding_preflight import _SubagentCodingPreflightMixin
from ._subagent_prompt import SubagentPromptMixin
from ._subagent_run import SubagentRunMixin
from ._subagent_status import SubagentStatusMixin
from ._subagent_tools import SubagentToolingMixin
from ._subagent_types import (
    AnnounceResultRequest,
    ArchiveRunRequest,
    DiagnosticRecord,
    FinalizeFailureRequest,
    FinalizeSuccessRequest,
    PrepareMessagesRequest,
    RunRequest,
    SpawnIssue,
    SpawnRequest,
    SpawnResult,
    SpawnTaskRef,
    StatusUpdate,
    SubagentAuxRuntimeConfig,
    SubagentManagerOptions,
    SubagentPromptRequest,
    TaskStatus,
    ToolCallExecutionRequest,
    ToolSetupResult,
)


class SubagentManager(
    SubagentStatusMixin,
    SubagentPromptMixin,
    _SubagentCodingPreflightMixin,
    SubagentToolingMixin,
    SubagentRunMixin,
):
    def __init__(self, provider: LLMProvider, options: SubagentManagerOptions):
        from bao.config.schema import ExecToolConfig

        self.provider = provider
        self.workspace = options.workspace
        self.bus = options.bus
        self.model = options.model or provider.get_default_model()
        self.temperature = options.temperature
        self.max_tokens = options.max_tokens
        self.reasoning_effort = options.reasoning_effort
        self.service_tier = options.service_tier
        self.search_config = options.search_config
        self.web_proxy = options.web_proxy
        self.exec_config = options.exec_config or ExecToolConfig()
        self.restrict_to_workspace = options.restrict_to_workspace
        self.image_generation_config = options.image_generation_config
        self.desktop_config = options.desktop_config
        self.browser_enabled = options.browser_enabled
        self.sessions = options.sessions
        self.max_iterations = max(1, int(options.max_iterations))
        self._ctx_mgmt = options.context_management
        self._tool_offload_chars = max(1, int(options.tool_output_offload_chars))
        self._tool_preview_chars = max(0, int(options.tool_output_preview_chars))
        self._tool_hard_chars = max(500, int(options.tool_output_hard_chars))
        self._compact_bytes = max(50000, int(options.context_compact_bytes_est))
        self._compact_keep_blocks = max(1, int(options.context_compact_keep_recent_tool_blocks))
        self._artifact_retention_days = max(1, int(options.artifact_retention_days))
        self._memory = options.memory_store
        self._memory_policy = options.memory_policy or DEFAULT_MEMORY_POLICY
        self._utility_provider = options.utility_provider
        self._utility_model = options.utility_model
        self._experience_mode = options.experience_mode.lower()
        self._artifact_cleanup_done = False
        self._runtime_diagnostics = get_runtime_diagnostics_store()
        self._running_tasks: dict[str, object] = {}
        self._task_statuses: dict[str, TaskStatus] = {}
        self._session_tasks: dict[str, set[str]] = {}

    def set_aux_runtime(self, config: SubagentAuxRuntimeConfig) -> None:
        self._utility_provider = config.utility_provider
        self._utility_model = config.utility_model
        self._experience_mode = (config.experience_mode or "utility").lower()


__all__ = [
    "AnnounceResultRequest",
    "ArchiveRunRequest",
    "DiagnosticRecord",
    "FinalizeFailureRequest",
    "FinalizeSuccessRequest",
    "PrepareMessagesRequest",
    "RunRequest",
    "SpawnIssue",
    "SpawnRequest",
    "SpawnResult",
    "SpawnTaskRef",
    "StatusUpdate",
    "SubagentAuxRuntimeConfig",
    "SubagentManager",
    "SubagentManagerOptions",
    "SubagentPromptRequest",
    "TaskStatus",
    "ToolCallExecutionRequest",
    "ToolSetupResult",
]
