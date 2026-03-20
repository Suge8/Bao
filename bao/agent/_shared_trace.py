"""Trace helper utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolTraceEntryRequest:
    trace_idx: int
    tool_name: str
    args_preview: str
    has_error: bool
    result: Any
    result_max_len: int = 100


def sanitize_visible_text(text: str) -> str:
    return text.replace("\n", " ").replace("\r", "").replace("|", "/")


def sanitize_trace_text(text: Any, max_len: int) -> str:
    normalized = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    compact = " ".join(normalized.split())
    return compact[:max_len]


def summarize_tool_args_for_trace(
    tool_name: str,
    args: dict[str, Any] | None,
    *,
    max_len: int = 60,
) -> str:
    payload = args or {}
    if tool_name in {"write_file", "edit_file"}:
        path = payload.get("path")
        return sanitize_trace_text(path if isinstance(path, str) else "<redacted>", max_len)
    if tool_name == "exec":
        command = payload.get("command")
        if isinstance(command, str):
            return f"<redacted:{len(command)} chars>"
    if tool_name in {"session_default", "session_lookup"}:
        query = payload.get("query")
        if isinstance(query, str) and query.strip():
            return sanitize_trace_text(query.strip(), max_len)
        channel = payload.get("channel")
        if isinstance(channel, str) and channel.strip():
            return sanitize_trace_text(f"channel={channel.strip()}", max_len)
    if tool_name in {"session_resolve", "send_to_session"}:
        session_ref = payload.get("session_ref")
        if isinstance(session_ref, str) and session_ref.strip():
            return sanitize_trace_text(f"session_ref={session_ref.strip()}", max_len)
        session_key = payload.get("session_key")
        if isinstance(session_key, str) and session_key.strip():
            return sanitize_trace_text(f"session_key={session_key.strip()}", max_len)
    first_arg = next(iter(payload.values()), "") if payload else ""
    return sanitize_trace_text(first_arg, max_len)


def build_tool_trace_entry(request: ToolTraceEntryRequest) -> str:
    safe_args = sanitize_trace_text(request.args_preview, 60)
    safe_result = sanitize_trace_text(request.result, request.result_max_len)
    status = "ERROR" if request.has_error else "ok"
    return f"T{request.trace_idx} {request.tool_name}({safe_args}) → {status}: {safe_result}"


def push_failed_direction(
    failed_directions: list[str],
    entry: str,
    *,
    max_items: int = 20,
) -> None:
    if failed_directions and failed_directions[-1] == entry:
        return
    failed_directions.append(entry)
    if len(failed_directions) > max_items:
        del failed_directions[:-max_items]
