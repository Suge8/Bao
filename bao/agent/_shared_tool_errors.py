"""Structured tool error parsing."""

from __future__ import annotations

import re

from bao.agent.protocol import ToolErrorCategory, ToolErrorInfo
from bao.agent.tool_result import SOFT_INTERRUPT_MESSAGE, ToolExecutionResult, tool_result_excerpt

from ._shared_tool_error_coding import parse_coding_agent_error, parse_web_fetch_payload
from ._shared_tool_error_types import (
    ToolErrorContext,
    ToolErrorSpec,
    build_tool_error_context,
    build_tool_error_info,
)


def parse_tool_error(
    tool_name: str,
    result: object,
    error_keywords: tuple[str, ...],
) -> ToolErrorInfo | None:
    result_text = tool_result_excerpt(result).strip()
    if not result_text:
        return None
    context = build_tool_error_context(tool_name, result_text)
    if isinstance(result, ToolExecutionResult):
        return _tool_execution_result_info(result, context)
    if result_text == SOFT_INTERRUPT_MESSAGE:
        return _interrupted_info(context, "soft_interrupt", SOFT_INTERRUPT_MESSAGE)
    if tool_name == "web_search":
        return _web_search_info(context)
    if tool_name == "web_fetch":
        return _web_fetch_info(context)
    for handler in (
        _invalid_params_info,
        _tool_not_found_info,
        _execution_prefix_info,
        lambda ctx: _exec_info(ctx, error_keywords),
        lambda ctx: parse_coding_agent_error(ctx, error_keywords),
        lambda ctx: _keyword_fallback_info(ctx, error_keywords),
    ):
        info = handler(context)
        if info is not None:
            return info
    return None


def has_tool_error(tool_name: str, result: object, error_keywords: tuple[str, ...]) -> bool:
    info = parse_tool_error(tool_name, result, error_keywords)
    return bool(info and info.is_error)


def _tool_execution_result_info(
    result: ToolExecutionResult,
    context: ToolErrorContext,
) -> ToolErrorInfo | None:
    spec = _tool_execution_result_spec(result)
    if spec is None:
        return None
    return build_tool_error_info(context, spec)


def _tool_execution_result_spec(result: ToolExecutionResult) -> ToolErrorSpec | None:
    if result.status == "interrupted":
        return ToolErrorSpec(
            is_error=False,
            category=ToolErrorCategory.INTERRUPTED,
            code=result.code or "soft_interrupt",
            retryable=False,
            message=result.message or SOFT_INTERRUPT_MESSAGE,
        )
    if result.status != "error":
        return None
    if result.code == "invalid_params":
        return ToolErrorSpec(
            category=ToolErrorCategory.INVALID_PARAMS,
            code=result.code,
            message=result.message or "Invalid tool parameters",
        )
    if result.code == "tool_not_found":
        return ToolErrorSpec(
            category=ToolErrorCategory.TOOL_NOT_FOUND,
            code=result.code,
            retryable=False,
            message=result.message or "Tool not found",
        )
    if result.code == "timeout":
        return ToolErrorSpec(
            category=ToolErrorCategory.TIMEOUT,
            code=result.code,
            message=result.message or "Tool timed out",
        )
    return ToolErrorSpec(
        category=ToolErrorCategory.EXECUTION_ERROR,
        code=result.code or "execution_error",
        message=result.message or "Error executing tool",
    )


def _interrupted_info(context: ToolErrorContext, code: str, message: str) -> ToolErrorInfo:
    return build_tool_error_info(
        context,
        ToolErrorSpec(
            is_error=False,
            category=ToolErrorCategory.INTERRUPTED,
            code=code,
            retryable=False,
            message=message,
        ),
    )


def _invalid_params_info(context: ToolErrorContext) -> ToolErrorInfo | None:
    if not context.result_normalized.startswith("error: invalid parameters for tool"):
        return None
    return build_tool_error_info(
        context,
        ToolErrorSpec(
            category=ToolErrorCategory.INVALID_PARAMS,
            code="invalid_params",
            message="Invalid tool parameters",
        ),
    )


def _tool_not_found_info(context: ToolErrorContext) -> ToolErrorInfo | None:
    if not context.result_normalized.startswith("error: tool '") or "not found" not in context.result_normalized:
        return None
    return build_tool_error_info(
        context,
        ToolErrorSpec(
            category=ToolErrorCategory.TOOL_NOT_FOUND,
            code="tool_not_found",
            retryable=False,
            message="Tool not found",
        ),
    )


def _execution_prefix_info(context: ToolErrorContext) -> ToolErrorInfo | None:
    if not context.result_normalized.startswith("error executing"):
        return None
    return _execution_error(
        context,
        ToolErrorSpec(
            category=ToolErrorCategory.EXECUTION_ERROR,
            code="execution_error",
            message="Error executing tool",
        ),
    )


def _web_search_info(context: ToolErrorContext) -> ToolErrorInfo | None:
    if context.tool_name != "web_search":
        return None
    if context.result_normalized.startswith("error executing"):
        return _execution_error(
            context,
            ToolErrorSpec(
                category=ToolErrorCategory.EXECUTION_ERROR,
                code="execution_error",
                message="Error executing tool",
            ),
        )
    if context.result_normalized.startswith("error:"):
        return _execution_error(
            context,
            ToolErrorSpec(
                category=ToolErrorCategory.EXECUTION_ERROR,
                code="web_search_error",
                message="Web search error",
            ),
        )
    return None


def _web_fetch_info(context: ToolErrorContext) -> ToolErrorInfo | None:
    if context.tool_name != "web_fetch":
        return None
    if context.result_normalized.startswith("error executing"):
        return _execution_error(
            context,
            ToolErrorSpec(
                category=ToolErrorCategory.EXECUTION_ERROR,
                code="execution_error",
                message="Error executing tool",
            ),
        )
    if context.result_normalized.startswith("error:"):
        return _execution_error(
            context,
            ToolErrorSpec(
                category=ToolErrorCategory.EXECUTION_ERROR,
                code="web_fetch_error",
                message="Web fetch error",
            ),
        )
    if not context.result_normalized.startswith("{"):
        return None
    payload = parse_web_fetch_payload(context.result_normalized)
    if payload == "malformed":
        return _execution_error(
            context,
            ToolErrorSpec(
                category=ToolErrorCategory.EXECUTION_ERROR,
                code="web_fetch_error",
                message="Web fetch JSON error (malformed)",
            ),
        )
    if isinstance(payload, dict) and payload.get("error"):
        return _execution_error(
            context,
            ToolErrorSpec(
                category=ToolErrorCategory.EXECUTION_ERROR,
                code="web_fetch_error",
                message="Web fetch JSON error",
            ),
        )
    return None


def _exec_info(context: ToolErrorContext, error_keywords: tuple[str, ...]) -> ToolErrorInfo | None:
    if context.tool_name != "exec":
        return None
    exit_match = re.search(r"exit\s*code\s*:\s*(-?\d+)", context.result_normalized)
    if exit_match:
        exit_code = _parse_exit_code(exit_match.group(1))
        if exit_code is not None and exit_code != 0:
            return _execution_error(
                context,
                ToolErrorSpec(
                    category=ToolErrorCategory.EXECUTION_ERROR,
                    code="exec_exit_code",
                    message=f"Exit code {exit_code}",
                    details={"exit_code": exit_code},
                ),
            )
    if any(keyword in context.result_lower for keyword in error_keywords):
        return _keyword_match_info(context)
    return None


def _keyword_fallback_info(
    context: ToolErrorContext,
    error_keywords: tuple[str, ...],
) -> ToolErrorInfo | None:
    if any(keyword in context.result_lower for keyword in error_keywords):
        return _keyword_match_info(context)
    return None


def _parse_exit_code(raw_exit_code: str) -> int | None:
    try:
        return int(raw_exit_code)
    except ValueError:
        return None


def _execution_error(context: ToolErrorContext, spec: ToolErrorSpec) -> ToolErrorInfo:
    return build_tool_error_info(context, spec)


def _keyword_match_info(context: ToolErrorContext) -> ToolErrorInfo:
    return build_tool_error_info(
        context,
        ToolErrorSpec(
            category=ToolErrorCategory.UNKNOWN,
            code="keyword_match",
            message="Error keyword detected",
        ),
    )
