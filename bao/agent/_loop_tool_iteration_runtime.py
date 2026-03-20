from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

from bao.agent import shared
from bao.agent.artifacts_models import ToolOutputBudgetRequest
from bao.agent.context import ToolResultMessage
from bao.agent.protocol import StreamEvent, StreamEventType
from bao.agent.tool_result import tool_result_payload

if TYPE_CHECKING:
    from bao.agent._loop_tool_iteration_mixin import LoopToolIterationMixin
    from bao.agent._loop_tool_iteration_support import ToolIterationRequest


@dataclass(slots=True)
class ToolCallResultRequest:
    iteration: "ToolIterationRequest"
    tool_call: Any
    raw_result: Any
    iter_completed: list[dict[str, Any]]
    args_preview: str


def prepare_tool_call(request: "ToolIterationRequest", tool_call: Any) -> str:
    if request.state.consecutive_errors > 0:
        request.counters.retry_attempts_proxy += 1
    request.tools_used.append(tool_call.name)
    args_preview = shared.summarize_tool_args_for_trace(
        tool_call.name,
        tool_call.arguments,
        max_len=200,
    )
    logger.info("🔧 工具调用 / tool: {}({})", tool_call.name, args_preview)
    return args_preview


async def emit_tool_start(request: "ToolIterationRequest", tool_name: str) -> None:
    if request.on_event is None:
        return
    await request.on_event(
        StreamEvent(type=StreamEventType.TOOL_START, meta={"tool_name": tool_name})
    )


async def execute_tool_call(
    loop: "LoopToolIterationMixin",
    request: "ToolIterationRequest",
    tool_call: Any,
    allowed_tool_names: set[str] | None,
) -> Any:
    return await loop._execute_tool_call(
        tool_call=tool_call,
        allowed_tool_names=allowed_tool_names,
        messages=request.messages,
        current_task_ref=request.current_task_ref,
    )


def record_tool_result(
    loop: "LoopToolIterationMixin",
    request: ToolCallResultRequest,
) -> tuple[str, bool]:
    iteration = request.iteration
    iteration.reply_attachments.extend(
        loop._archive_reply_attachments(
            tool_name=request.tool_call.name,
            artifact_session_key=iteration.artifact_session_key,
            artifact_store=iteration.artifact_store,
            raw_result=request.raw_result,
        )
    )
    tool_error = loop._update_tool_error_counters(
        tool_name=request.tool_call.name,
        raw_result=request.raw_result,
        counters=iteration.counters,
        artifact_session_key=iteration.artifact_session_key,
    )
    result, budget_event = iteration.apply_tool_output_budget(
        _build_budget_request(loop, request)
    )
    _apply_budget_event(iteration.tool_budget, budget_event)
    result, screenshot_image_b64 = loop._handle_screenshot_marker(request.tool_call.name, result)
    _append_tool_result(loop, request, result, screenshot_image_b64)
    has_error = bool(tool_error and tool_error.is_error)
    is_interrupted = bool(tool_error and tool_error.category == "interrupted")
    _update_tool_state(loop, request, result, has_error, is_interrupted)
    return result, has_error


def _append_tool_result(
    loop: "LoopToolIterationMixin",
    request: ToolCallResultRequest,
    result: str,
    screenshot_image_b64: str | None,
) -> None:
    iteration = request.iteration
    iteration.messages = loop.context.add_tool_result(
        iteration.messages,
        ToolResultMessage(
            tool_call_id=request.tool_call.id,
            tool_name=request.tool_call.name,
            result=result,
            image_base64=screenshot_image_b64,
        ),
    )
    request.iter_completed.append(
        {
            "role": "tool",
            "tool_call_id": request.tool_call.id,
            "name": request.tool_call.name,
            "content": result,
        }
    )


def _update_tool_state(
    loop: "LoopToolIterationMixin",
    request: ToolCallResultRequest,
    result: str,
    has_error: bool,
    is_interrupted: bool,
) -> None:
    loop._record_tool_trace(
        request,
        result=result,
        has_error=has_error,
    )
    loop._update_tool_state_after_call(
        request,
        has_error=has_error,
        is_interrupted=is_interrupted,
    )


def _build_budget_request(
    loop: "LoopToolIterationMixin",
    request: ToolCallResultRequest,
) -> ToolOutputBudgetRequest:
    iteration = request.iteration
    return ToolOutputBudgetRequest(
        store=iteration.artifact_store,
        tool_name=request.tool_call.name,
        tool_call_id=request.tool_call.id,
        result=tool_result_payload(request.raw_result),
        offload_chars=loop._tool_offload_chars,
        preview_chars=loop._tool_preview_chars,
        hard_chars=loop._tool_hard_chars,
        ctx_mgmt=loop._ctx_mgmt,
    )


async def emit_tool_end(
    request: "ToolIterationRequest",
    tool_name: str,
    has_error: bool,
) -> None:
    if request.on_event is None:
        return
    await request.on_event(
        StreamEvent(
            type=StreamEventType.TOOL_END,
            meta={"tool_name": tool_name, "has_error": has_error},
        )
    )


def interrupt_at_tool_boundary(
    loop: "LoopToolIterationMixin",
    request: "ToolIterationRequest",
    iter_completed: list[dict[str, Any]],
) -> bool:
    if not loop._is_soft_interrupted(request.current_task_ref):
        return False
    if iter_completed:
        request.completed_tool_msgs.extend(iter_completed)
    logger.debug(
        "Interrupted at tool boundary in session {}",
        request.artifact_session_key,
    )
    request.state.interrupted = True
    return True


def _apply_budget_event(tool_budget: dict[str, int], budget_event: Any) -> None:
    if budget_event.offloaded:
        tool_budget["offloaded_count"] += 1
        tool_budget["offloaded_chars"] += budget_event.offloaded_chars
    if budget_event.hard_clipped:
        tool_budget["clipped_count"] += 1
        tool_budget["clipped_chars"] += budget_event.hard_clipped_chars
