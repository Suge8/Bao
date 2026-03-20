from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from bao.agent import shared
from bao.agent._loop_constants import ERROR_KEYWORDS as _ERROR_KEYWORDS
from bao.agent._loop_tool_iteration_runtime import ToolCallResultRequest
from bao.agent._loop_tool_iteration_support import (
    ToolIterationRequest,
    prepare_tool_iteration,
    process_tool_call,
)
from bao.agent._loop_types import ToolObservabilityCounters as _ToolObservabilityCounters
from bao.agent.context import AssistantMessageSpec
from bao.agent.run_controller import RunLoopState, build_error_feedback
from bao.agent.tool_result import ToolExecutionResult
from bao.runtime_diagnostics_models import RuntimeEventRequest


class LoopToolIterationMixin:
    async def _handle_tool_call_iteration(self, request: ToolIterationRequest) -> list[dict[str, Any]]:
        iter_completed: list[dict[str, Any]] = []
        allowed_tool_names = request.tool_exposure.allowed_tool_names()
        await prepare_tool_iteration(self, request, iter_completed)
        if request.state.interrupted:
            return request.messages
        for tool_call in request.response.tool_calls:
            interrupted = await process_tool_call(
                self, request, tool_call, allowed_tool_names, iter_completed
            )
            if interrupted:
                break
        error_feedback = build_error_feedback(
            request.state.consecutive_errors,
            request.failed_directions,
        )
        if error_feedback:
            request.messages.append({"role": "user", "content": error_feedback})
        if iter_completed and not request.state.interrupted:
            request.completed_tool_msgs.extend(iter_completed)
        if self._is_soft_interrupted(request.current_task_ref):
            request.state.interrupted = True
        return request.messages

    async def _execute_tool_call(
        self,
        *,
        tool_call: Any,
        allowed_tool_names: set[str] | None,
        messages: list[dict[str, Any]],
        current_task_ref: asyncio.Task[None] | None,
    ) -> Any:
        if allowed_tool_names is not None and tool_call.name not in allowed_tool_names:
            allowed_names = sorted(allowed_tool_names)
            preview = ", ".join(allowed_names[:10]) if allowed_names else "none"
            overflow = len(allowed_names) - 10
            allowed = f"{preview}, ... (+{overflow} more)" if overflow > 0 else preview
            return ToolExecutionResult.error(
                code="tool_not_found",
                message="Tool not found",
                value=f"Error: Tool '{tool_call.name}' not found. Available tools: {allowed}.\n\n[Analyze the error above and try a different approach.]",
            )
        tool_task = asyncio.create_task(
            self.tools.execute(
                tool_call.name,
                tool_call.arguments,
                raw_arguments=tool_call.raw_arguments,
                argument_parse_error=tool_call.argument_parse_error,
            )
        )
        return await self._await_tool_with_interrupt(tool_task, current_task_ref)
    def _update_tool_error_counters(self, *, tool_name: str, raw_result: Any, counters: _ToolObservabilityCounters, artifact_session_key: str | None) -> Any:
        tool_error = shared.parse_tool_error(tool_name, raw_result, _ERROR_KEYWORDS)
        if not tool_error:
            return None
        category_to_field = {
            "invalid_params": "invalid_parameter_errors",
            "tool_not_found": "tool_not_found_errors",
            "execution_error": "execution_errors",
            "interrupted": "interrupted_tool_calls",
        }
        field_name = category_to_field.get(tool_error.category)
        if field_name:
            setattr(counters, field_name, getattr(counters, field_name) + 1)
        if tool_error.is_error:
            self._record_runtime_diagnostic(
                RuntimeEventRequest(
                    source="tool",
                    stage="tool_call",
                    message=tool_error.message,
                    code=tool_error.code or tool_error.category,
                    retryable=tool_error.retryable,
                    session_key=artifact_session_key or "",
                    details={
                        "tool_name": tool_name,
                        "excerpt": tool_error.raw_excerpt,
                        **tool_error.details,
                    },
                )
            )
        return tool_error
    def _record_tool_trace(
        self,
        request: ToolCallResultRequest,
        *,
        result: Any,
        has_error: bool,
    ) -> None:
        trace_idx = len(request.iteration.tool_trace) + 1
        trace_entry = shared.build_tool_trace_entry(
            shared.ToolTraceEntryRequest(
                trace_idx=trace_idx,
                tool_name=request.tool_call.name,
                args_preview=request.args_preview,
                has_error=has_error,
                result=result,
            )
        )
        request.iteration.tool_trace.append(trace_entry)
        request.iteration.sufficiency_trace.append(trace_entry)
        if len(request.iteration.sufficiency_trace) > 32:
            del request.iteration.sufficiency_trace[:-32]
        request.iteration.state.total_tool_steps_for_sufficiency += 1

    def _update_tool_state_after_call(
        self,
        request: ToolCallResultRequest,
        *,
        has_error: bool,
        is_interrupted: bool,
    ) -> None:
        state = request.iteration.state
        if has_error:
            state.total_errors += 1
            state.consecutive_errors += 1
            failed_preview = shared.summarize_tool_args_for_trace(
                request.tool_call.name,
                request.tool_call.arguments,
                max_len=80,
            )
            shared.push_failed_direction(
                request.iteration.failed_directions,
                f"{request.tool_call.name}({failed_preview})",
            )
            return
        state.consecutive_errors = 0
        if not is_interrupted:
            request.iteration.counters.tool_calls_ok += 1
    def _handle_final_response_iteration(
        self,
        *,
        response: Any,
        messages: list[dict[str, Any]],
        current_task_ref: asyncio.Task[None] | None,
        artifact_session_key: str | None,
        state: RunLoopState,
    ) -> tuple[list[dict[str, Any]], bool]:
        if self._is_soft_interrupted(current_task_ref):
            state.interrupted = True
            return messages, False
        clean_final = self._strip_think(response.content)
        if response.finish_reason == "error":
            logger.error("LLM returned error: {}", (clean_final or "")[:200])
            safe_error = clean_final or "Sorry, I encountered an error calling the AI model."
            self._record_runtime_diagnostic(
                RuntimeEventRequest(
                    source="provider",
                    stage="chat",
                    message=safe_error,
                    code="provider_error",
                    retryable=True,
                    session_key=artifact_session_key or "",
                    details={"finish_reason": response.finish_reason},
                )
            )
            state.final_content = safe_error
            state.provider_error = True
            return messages, False
        state.force_final_response, state.force_final_backoff_used, retry_prompt = shared.maybe_backoff_empty_final(
            force_final_response=state.force_final_response,
            force_final_backoff_used=state.force_final_backoff_used,
            clean_final=clean_final,
        )
        if retry_prompt is not None:
            messages.append(retry_prompt)
            return messages, True
        state.final_content = clean_final
        messages = self.context.add_assistant_message(
            messages,
            AssistantMessageSpec(
                content=clean_final,
                reasoning_content=response.reasoning_content,
                thinking_blocks=response.thinking_blocks,
            ),
        )
        return messages, False
