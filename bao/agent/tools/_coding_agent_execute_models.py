from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExecuteRequest:
    prompt_text: str
    project_path: str | None
    session_id: str | None
    continue_session: bool
    model: str | None
    timeout: int
    response_format: str
    max_output_chars: int
    include_details: bool
    extra_params: dict[str, Any]
    request_id: str
    context_key: str


@dataclass(frozen=True)
class PreparedExecuteRequest:
    request: ExecuteRequest
    cwd: Path
    resolved_session: str | None
    session_source: str


@dataclass(frozen=True)
class CommandOutcome:
    request: ExecuteRequest
    prepared: PreparedExecuteRequest
    command_preview: str
    attempts: int
    duration_ms: int
    stdout_text: str
    stderr_text: str
    final_output: str
    detail_stdout: str
    return_code: int | None


@dataclass(frozen=True)
class TimeoutOutcome:
    request: ExecuteRequest
    prepared: PreparedExecuteRequest
    command_preview: str
    attempts: int
    duration_ms: int
