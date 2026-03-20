"""Shared tool error context and construction helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bao.agent.protocol import ToolErrorInfo

from ._shared_trace import sanitize_trace_text


@dataclass(frozen=True)
class ToolErrorContext:
    tool_name: str
    result_text: str
    result_lower: str
    result_normalized: str
    excerpt: str


@dataclass(frozen=True)
class ToolErrorSpec:
    category: str
    code: str | None = None
    retryable: bool = True
    message: str = ""
    is_error: bool = True
    details: dict[str, Any] | None = None


def build_tool_error_context(tool_name: str, result_text: str) -> ToolErrorContext:
    result_lower = result_text.lower()
    return ToolErrorContext(
        tool_name=tool_name,
        result_text=result_text,
        result_lower=result_lower,
        result_normalized=result_lower.lstrip(),
        excerpt=sanitize_trace_text(result_text, 200),
    )


def build_tool_error_info(context: ToolErrorContext, spec: ToolErrorSpec) -> ToolErrorInfo:
    return ToolErrorInfo(
        is_error=spec.is_error,
        tool_name=context.tool_name,
        category=spec.category,
        code=spec.code,
        retryable=spec.retryable,
        message=spec.message or spec.category,
        raw_excerpt=context.excerpt,
        details=spec.details or {},
    )
