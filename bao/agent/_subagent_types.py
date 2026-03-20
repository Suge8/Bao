from __future__ import annotations

import re

from ._subagent_model_types import (
    SpawnIssue,
    SpawnResult,
    SpawnResultStatus,
    SpawnTaskRef,
    TaskStatus,
)
from ._subagent_request_types import (
    AnnounceResultRequest,
    ArchiveRunRequest,
    CodingProgressSetupRequest,
    DiagnosticRecord,
    FinalizeFailureRequest,
    FinalizeSuccessRequest,
    PreIterationRequest,
    PrepareMessagesRequest,
    RunRequest,
    SpawnRequest,
    StatusUpdate,
    SubagentAuxRuntimeConfig,
    SubagentManagerOptions,
    SubagentPromptRequest,
    ToolCallExecutionRequest,
    ToolSetupResult,
)

_SUBAGENT_ERROR_KEYWORDS = ("error:", "traceback", "failed", "exception", "permission denied")
_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

__all__ = [
    "_ANSI_ESCAPE_RE",
    "_SUBAGENT_ERROR_KEYWORDS",
    "AnnounceResultRequest",
    "ArchiveRunRequest",
    "CodingProgressSetupRequest",
    "DiagnosticRecord",
    "FinalizeFailureRequest",
    "FinalizeSuccessRequest",
    "PreIterationRequest",
    "PrepareMessagesRequest",
    "RunRequest",
    "SpawnIssue",
    "SpawnRequest",
    "SpawnResult",
    "SpawnResultStatus",
    "SpawnTaskRef",
    "StatusUpdate",
    "SubagentAuxRuntimeConfig",
    "SubagentManagerOptions",
    "SubagentPromptRequest",
    "TaskStatus",
    "ToolCallExecutionRequest",
    "ToolSetupResult",
]
