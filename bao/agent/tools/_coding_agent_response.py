from __future__ import annotations

import json
from typing import Any

from bao.agent.tool_result import ToolResultValue, maybe_temp_text_result


def trim_for_summary(text: str, max_chars: int) -> str:
    body = text.strip()
    if len(body) <= max_chars:
        return body
    omitted = len(body) - max_chars
    return body[:max_chars] + f"\n... (truncated, {omitted} more chars)"


def summarize_output(stdout_text: str, stderr_text: str, max_chars: int = 1600) -> str:
    stdout_clean = stdout_text.strip()
    stderr_clean = stderr_text.strip()
    if stdout_clean and stderr_clean:
        return f"{trim_for_summary(stdout_clean, max_chars)}\n\nSTDERR:\n{trim_for_summary(stderr_clean, max_chars)}"
    if stdout_clean:
        return trim_for_summary(stdout_clean, max_chars)
    if stderr_clean:
        return f"STDERR:\n{trim_for_summary(stderr_clean, max_chars)}"
    return "(no output)"


def timeout_error_guidance(timeout_seconds: int, max_timeout_seconds: int) -> str:
    if timeout_seconds >= max_timeout_seconds:
        return (
            f"Timeout is already at the {max_timeout_seconds}-second maximum. "
            "Inspect details output or reduce the task scope before retrying."
        )
    return "Retry and increase timeout_seconds if the task is expected to take longer."


def timeout_retry_hint(timeout_seconds: int, max_timeout_seconds: int) -> str:
    if timeout_seconds >= max_timeout_seconds:
        return "Timeout already reached the configured maximum; split the task into smaller steps."
    return f"Retry with a larger timeout_seconds value than {timeout_seconds} if needed."


def transient_retry_hint(timeout_seconds: int, max_timeout_seconds: int) -> str:
    if timeout_seconds >= max_timeout_seconds:
        return "Transient failure detected; retry once after verifying auth/network state."
    return "Transient failure detected; retry once or raise timeout_seconds if the backend was slow."


def build_details_hint(
    *,
    tool_name: str,
    request_id: str,
    session_id: str | None,
    include_details: bool,
    details_available: bool,
) -> str | None:
    if include_details or not details_available:
        return None
    session_hint = f" or session_id '{session_id}'" if session_id else ""
    return (
        "Detailed output omitted to protect context budget. "
        f"Use {tool_name}_details with request_id '{request_id}'{session_hint}."
    )


def _build_text_parts(
    *,
    payload: dict[str, Any],
    meta_prefix: str,
    response_format: str,
    extra_meta_fields: dict[str, Any] | None,
) -> list[str]:
    parts = [str(payload.get("message", ""))]
    if response_format == "hybrid":
        meta_payload = dict(payload)
        if extra_meta_fields:
            meta_payload.update(extra_meta_fields)
        parts.append(f"{meta_prefix}=" + json.dumps(meta_payload, ensure_ascii=False))
    summary = str(payload.get("summary") or "").strip()
    if summary:
        parts.append("Summary:\n" + summary)
    stdout_text = str(payload.get("stdout") or "").strip()
    stderr_text = str(payload.get("stderr") or "").strip()
    if stdout_text:
        parts.append("Output:\n" + stdout_text)
    if stderr_text:
        parts.append("STDERR:\n" + stderr_text)
    hints = [str(hint).strip() for hint in payload.get("hints", []) if str(hint).strip()]
    if hints:
        parts.append("Hints:\n" + "\n".join(f"- {hint}" for hint in hints))
    return [part for part in parts if part]


def render_payload(
    *,
    payload: dict[str, Any],
    response_format: str,
    meta_prefix: str,
    extra_meta_fields: dict[str, Any] | None = None,
) -> ToolResultValue:
    if response_format == "json":
        return maybe_temp_text_result(
            json.dumps(payload, ensure_ascii=False),
            prefix="bao_coding_agent_",
        )
    text = "\n\n".join(
        _build_text_parts(
            payload=payload,
            meta_prefix=meta_prefix,
            response_format=response_format,
            extra_meta_fields=extra_meta_fields,
        )
    )
    return maybe_temp_text_result(text, prefix="bao_coding_agent_")
