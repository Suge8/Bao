"""Structured tool-error protocol types.

Pure data definitions — no runtime dependencies outside the stdlib.
"""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field
from typing import Any


class ToolErrorCategory:
    """Stable string constants for tool error classification."""

    INVALID_PARAMS = "invalid_params"
    TOOL_NOT_FOUND = "tool_not_found"
    EXECUTION_ERROR = "execution_error"
    INTERRUPTED = "interrupted"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ToolErrorInfo:
    """Structured result of tool-error analysis.

    ``is_error=False`` means the tool invocation was *not* a failure
    (e.g. soft-interrupt cancellation).  Callers that only need a boolean
    should check ``info.is_error``, **not** ``info is not None``.
    """

    is_error: bool
    tool_name: str
    category: str  # one of ToolErrorCategory values
    code: str | None  # stable short code, e.g. "exec_exit_code", "mcp_error"
    retryable: bool
    message: str  # human-readable short message
    raw_excerpt: str  # sanitized excerpt of original result
    details: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class StreamEvent:
    """Structured agent stream event (schema version 1).

    Only ``delta``, ``reset``, and ``tool_hint`` map to on_progress/channel
    visible text.  All other types are on_event-only (avoid channel spam).
    """

    type: str  # see StreamEventType constants below
    text: str | None = None   # only delta / tool_hint / reset carry text
    meta: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=_time.time)


class StreamEventType:
    """Stable string constants for StreamEvent.type."""

    DELTA = "delta"
    RESET = "reset"
    TOOL_HINT = "tool_hint"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    TASK_STATUS = "task_status"
    ERROR = "error"
    FINAL = "final"
