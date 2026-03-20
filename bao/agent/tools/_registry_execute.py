from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bao.agent.tool_result import ToolExecutionResult
from bao.agent.tools.base import Tool


@dataclass(frozen=True)
class ToolExecutionRequest:
    name: str
    params: dict[str, Any]
    raw_arguments: str | None = None
    argument_parse_error: str | None = None


def tool_not_found_result(
    request: ToolExecutionRequest,
    *,
    available_tools_text: str,
) -> ToolExecutionResult:
    return ToolExecutionResult.error(
        code="tool_not_found",
        message="Tool not found",
        value=(
            f"Error: Tool '{request.name}' not found. Available tools: {available_tools_text}.\n\n"
            "[Analyze the error above and try a different approach.]"
        ),
    )


def invalid_params_result(
    request: ToolExecutionRequest,
    *,
    detail: str,
) -> ToolExecutionResult:
    raw_suffix = ""
    if isinstance(request.raw_arguments, str) and request.raw_arguments.strip():
        raw_preview = request.raw_arguments.strip()
        if len(raw_preview) > 200:
            raw_preview = raw_preview[:200] + "..."
        raw_suffix = f" Raw arguments: {raw_preview}"
    return ToolExecutionResult.error(
        code="invalid_params",
        message="Invalid tool parameters",
        value=(
            f"Error: Invalid parameters for tool '{request.name}': {detail}.{raw_suffix}\n\n"
            "[Analyze the error above and try a different approach.]"
        ),
    )
def execution_error_result(request: ToolExecutionRequest, *, error: Exception) -> ToolExecutionResult:
    return ToolExecutionResult.error(
        code="execution_error",
        message=f"Error executing {request.name}: {str(error)}",
        value=f"Error executing {request.name}: {str(error)}\n\n[Analyze the error above and try a different approach.]",
    )


def prepare_tool_execution(
    request: ToolExecutionRequest,
    *,
    tool: Tool,
) -> dict[str, Any] | ToolExecutionResult:
    cast_params = tool.cast_params(request.params)
    errors = tool.validate_params(cast_params)
    if errors:
        return invalid_params_result(request, detail="; ".join(errors))
    return cast_params
