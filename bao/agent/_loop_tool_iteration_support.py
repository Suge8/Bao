from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from bao.agent._loop_tool_iteration_runtime import (
    ToolCallResultRequest,
    emit_tool_end,
    emit_tool_start,
    execute_tool_call,
    interrupt_at_tool_boundary,
    prepare_tool_call,
    record_tool_result,
)
from bao.agent._loop_types import ToolObservabilityCounters
from bao.agent.artifacts_models import ToolOutputBudgetEvent, ToolOutputBudgetRequest
from bao.agent.context import AssistantMessageSpec
from bao.agent.protocol import StreamEvent, StreamEventType
from bao.agent.run_controller import RunLoopState
from bao.agent.tool_exposure import ToolExposureSnapshot

if TYPE_CHECKING:
    from bao.agent._loop_tool_iteration_mixin import LoopToolIterationMixin


@dataclass(slots=True)
class ToolIterationRequest:
    response: Any
    messages: list[dict[str, Any]]
    tool_exposure: ToolExposureSnapshot
    on_tool_hint: Callable[[str], Awaitable[None]] | None
    current_task_ref: asyncio.Task[None] | None
    artifact_session_key: str | None
    artifact_store: Any
    apply_tool_output_budget: Callable[[ToolOutputBudgetRequest], tuple[str, ToolOutputBudgetEvent]]
    state: RunLoopState
    counters: ToolObservabilityCounters
    tools_used: list[str]
    tool_trace: list[str]
    reasoning_snippets: list[str]
    failed_directions: list[str]
    sufficiency_trace: list[str]
    completed_tool_msgs: list[dict[str, Any]]
    reply_attachments: list[dict[str, Any]]
    tool_budget: dict[str, int]
    on_event: Callable[[StreamEvent], Awaitable[None]] | None = None
    on_visible_assistant_turn: Callable[[str], Awaitable[None]] | None = None
    tool_hint_lang: str | None = None


async def prepare_tool_iteration(
    loop: LoopToolIterationMixin,
    request: ToolIterationRequest,
    iter_completed: list[dict[str, Any]],
) -> None:
    clean = loop._strip_think(request.response.content)
    if clean:
        request.reasoning_snippets.append(clean[:200])
        if request.on_visible_assistant_turn is not None:
            await request.on_visible_assistant_turn(clean)
    await emit_tool_hint(loop, request)
    tool_call_dicts = [tc.to_openai_tool_call() for tc in request.response.tool_calls]
    request.messages = loop.context.add_assistant_message(
        request.messages,
        AssistantMessageSpec(
            content=request.response.content,
            tool_calls=tool_call_dicts,
            reasoning_content=request.response.reasoning_content,
            thinking_blocks=request.response.thinking_blocks,
        ),
    )
    iter_completed.append(
        {"role": "assistant", "content": clean or None, "tool_calls": tool_call_dicts}
    )
    if loop._is_soft_interrupted(request.current_task_ref):
        request.state.interrupted = True


async def emit_tool_hint(loop: LoopToolIterationMixin, request: ToolIterationRequest) -> None:
    if request.on_tool_hint is None:
        return
    hint_text = loop._tool_hint(request.response.tool_calls, lang=request.tool_hint_lang)
    if hint_text and request.on_visible_assistant_turn is not None and loop._tool_hints_enabled():
        await request.on_visible_assistant_turn(hint_text)
    await request.on_tool_hint(hint_text)
    if request.on_event is not None:
        await request.on_event(
            StreamEvent(
                type=StreamEventType.TOOL_HINT,
                text=hint_text,
                meta={"tool_names": [tc.name for tc in request.response.tool_calls]},
            )
        )


async def process_tool_call(
    loop: LoopToolIterationMixin,
    request: ToolIterationRequest,
    tool_call: Any,
    allowed_tool_names: set[str] | None,
    iter_completed: list[dict[str, Any]],
) -> bool:
    args_preview = prepare_tool_call(request, tool_call)
    await emit_tool_start(request, tool_call.name)
    raw_result = await execute_tool_call(loop, request, tool_call, allowed_tool_names)
    _result, has_error = record_tool_result(
        loop,
        ToolCallResultRequest(
            iteration=request,
            tool_call=tool_call,
            raw_result=raw_result,
            iter_completed=iter_completed,
            args_preview=args_preview,
        ),
    )
    await emit_tool_end(request, tool_call.name, has_error)
    return interrupt_at_tool_boundary(loop, request, iter_completed)
