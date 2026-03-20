"""Coding-agent-specific tool error parsing."""

from __future__ import annotations

import json
import re
from typing import Any

from bao.agent.protocol import ToolErrorCategory, ToolErrorInfo

from ._shared_tool_error_types import (
    ToolErrorContext,
    ToolErrorSpec,
    build_tool_error_info,
)


def parse_coding_agent_error(
    context: ToolErrorContext,
    error_keywords: tuple[str, ...],
) -> ToolErrorInfo | None:
    if context.tool_name not in {"coding_agent", "coding_agent_details"}:
        return None
    payload = _coding_agent_payload(context.result_normalized)
    if isinstance(payload, dict):
        status_error = _coding_agent_status_error(context, payload)
        if status_error is not None:
            return status_error
        exit_error = _coding_agent_exit_info(context, payload)
        if exit_error is not None:
            return exit_error
        timeout_error = _coding_agent_timeout_info(context, payload)
        if timeout_error is not None:
            return timeout_error
    if any(keyword in context.result_lower for keyword in error_keywords):
        return _unknown_keyword_info(context)
    return None


def parse_web_fetch_payload(result_normalized: str) -> dict[str, Any] | str | None:
    try:
        return json.loads(result_normalized)
    except json.JSONDecodeError:
        if re.match(r'^\{\s*"error"\s*:', result_normalized):
            return "malformed"
        return None


def _coding_agent_payload(result_normalized: str) -> dict[str, Any] | None:
    if result_normalized.startswith("{"):
        return _load_json_fragment(result_normalized)
    if "{" not in result_normalized or "}" not in result_normalized:
        return None
    start = result_normalized.find("{")
    end = result_normalized.rfind("}") + 1
    if not (0 <= start < end):
        return None
    return _load_json_fragment(result_normalized[start:end])


def _load_json_fragment(fragment: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(fragment)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _coding_agent_status_error(
    context: ToolErrorContext,
    payload: dict[str, Any],
) -> ToolErrorInfo | None:
    status = payload.get("status")
    if isinstance(status, str) and status.lower() in {"error", "failed"}:
        return _execution_error(
            context,
            ToolErrorSpec(
                category=ToolErrorCategory.EXECUTION_ERROR,
                code="coding_agent_status",
                message=f"Coding agent status: {status}",
            ),
        )
    if payload.get("error"):
        return _execution_error(
            context,
            ToolErrorSpec(
                category=ToolErrorCategory.EXECUTION_ERROR,
                code="coding_agent_error",
                message="Coding agent error field set",
            ),
        )
    return None


def _coding_agent_exit_info(
    context: ToolErrorContext,
    payload: dict[str, Any],
) -> ToolErrorInfo | None:
    for key in ("exit_code", "exitcode", "exitCode", "returncode", "return_code"):
        code_val = payload.get(key)
        if isinstance(code_val, int) and code_val != 0:
            return _execution_error(
                context,
                ToolErrorSpec(
                    category=ToolErrorCategory.EXECUTION_ERROR,
                    code="coding_agent_exit_code",
                    message=f"Coding agent exit code {code_val}",
                    details={"exit_code": code_val},
                ),
            )
    return None


def _coding_agent_timeout_info(
    context: ToolErrorContext,
    payload: dict[str, Any],
) -> ToolErrorInfo | None:
    for key in ("timed_out", "timedout", "timedOut"):
        timed_out = payload.get(key)
        if isinstance(timed_out, bool) and timed_out:
            return build_tool_error_info(
                context,
                ToolErrorSpec(
                    category=ToolErrorCategory.TIMEOUT,
                    code="coding_agent_timeout",
                    message="Coding agent timed out",
                ),
            )
    return None


def _execution_error(context: ToolErrorContext, spec: ToolErrorSpec) -> ToolErrorInfo:
    return build_tool_error_info(context, spec)


def _unknown_keyword_info(context: ToolErrorContext) -> ToolErrorInfo:
    return build_tool_error_info(
        context,
        ToolErrorSpec(
            category=ToolErrorCategory.UNKNOWN,
            code="keyword_match",
            message="Error keyword detected",
        ),
    )
