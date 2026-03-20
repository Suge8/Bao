from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ToolObservabilityCounters:
    schema_samples: int = 0
    schema_tool_count_last: int = 0
    schema_tool_count_max: int = 0
    schema_bytes_last: int = 0
    schema_bytes_max: int = 0
    schema_bytes_total: int = 0
    tool_calls_ok: int = 0
    invalid_parameter_errors: int = 0
    tool_not_found_errors: int = 0
    execution_errors: int = 0
    interrupted_tool_calls: int = 0
    retry_attempts_proxy: int = 0


@dataclass
class ProcessMessageRunResult:
    final_content: str | None
    tools_used: list[str]
    tool_trace: list[str]
    total_errors: int
    reasoning_snippets: list[str]
    provider_error: bool
    interrupted: bool
    completed_tool_msgs: list[dict[str, Any]]
    reply_attachments: list[dict[str, Any]]


@dataclass(frozen=True)
class BackgroundTurnInput:
    session_key: str
    origin_channel: str
    origin_chat_id: str
    system_prompt_text: str
    search_query: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TurnExecutionOutcome:
    parsed_result: ProcessMessageRunResult
    final_content: str


def extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content) if content else ""


def archive_all_signature(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return ""
    tail_ts = str(messages[-1].get("timestamp", ""))
    return f"{len(messages)}:{tail_ts}"


def reply_attachment_name_hint(tool_name: str, file_name: str) -> str:
    stem = Path(file_name).stem.strip() or "attachment"
    return f"{tool_name}_{stem}"
