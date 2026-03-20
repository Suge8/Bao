from __future__ import annotations

from typing import Any

from loguru import logger

from bao.agent._loop_run_loop_support import (
    archive_run_artifact,
    build_chat_request,
    build_run_loop_context,
    build_run_loop_result,
    finalize_tool_observability,
)
from bao.agent._loop_run_models import (
    ArchiveRunArtifactRequest,
    FinalizeToolObservabilityRequest,
    RunAgentLoopOptions,
    RunLoopContext,
)
from bao.agent._loop_tool_iteration_mixin import ToolIterationRequest
from bao.agent._loop_tool_runtime_models import LoopPreIterationRequest


class LoopRunLoopMixin:
    def _finalize_tool_observability(self, request: FinalizeToolObservabilityRequest) -> None:
        finalize_tool_observability(self, request)

    async def _prepare_run_loop_iteration(
        self,
        *,
        initial_messages: list[dict[str, Any]],
        ctx: RunLoopContext,
        options: RunAgentLoopOptions,
    ) -> tuple[Any, Any] | None:
        ctx.messages = await self._apply_pre_iteration_checks(
            LoopPreIterationRequest(
                messages=ctx.messages,
                initial_messages=initial_messages,
                current_task_ref=ctx.current_task_ref,
                user_request=ctx.user_request,
                artifact_store=ctx.artifact_store,
                state=ctx.state,
                tool_trace=ctx.tool_trace,
                reasoning_snippets=ctx.reasoning_snippets,
                failed_directions=ctx.failed_directions,
                sufficiency_trace=ctx.sufficiency_trace,
            )
        )
        if ctx.state.interrupted:
            return None
        response, tool_exposure = await self._chat_once_with_selected_tools(
            build_chat_request(
                initial_messages=initial_messages,
                ctx=ctx,
                options=options,
            )
        )
        ctx.last_tool_exposure = tool_exposure
        ctx.tool_exposure_history.append(tool_exposure)
        ctx.provider_finish_reason = str(response.finish_reason or "")
        logger.debug(
            "LLM response: model={}, has_tool_calls={}, tool_count={}, finish_reason={}",
            self.model,
            response.has_tool_calls,
            len(response.tool_calls),
            response.finish_reason,
        )
        return response, tool_exposure

    async def _handle_run_loop_response(
        self,
        *,
        response: Any,
        tool_exposure: Any,
        initial_messages: list[dict[str, Any]],
        ctx: RunLoopContext,
        options: RunAgentLoopOptions,
    ) -> bool:
        from bao.agent.artifacts import apply_tool_output_budget

        if response.finish_reason == "interrupted":
            ctx.state.interrupted = True
            return False
        if response.has_tool_calls:
            ctx.messages = await self._handle_tool_call_iteration(
                ToolIterationRequest(
                    response=response,
                    messages=ctx.messages,
                    tool_exposure=tool_exposure,
                    on_tool_hint=options.on_tool_hint,
                    current_task_ref=ctx.current_task_ref,
                    artifact_session_key=options.artifact_session_key,
                    artifact_store=ctx.artifact_store,
                    apply_tool_output_budget=apply_tool_output_budget,
                    state=ctx.state,
                    counters=ctx.counters,
                    tools_used=ctx.tools_used,
                    tool_trace=ctx.tool_trace,
                    reasoning_snippets=ctx.reasoning_snippets,
                    failed_directions=ctx.failed_directions,
                    sufficiency_trace=ctx.sufficiency_trace,
                    completed_tool_msgs=ctx.completed_tool_msgs,
                    reply_attachments=ctx.reply_attachments,
                    tool_budget=ctx.tool_budget,
                    on_event=options.on_event,
                    on_visible_assistant_turn=options.on_visible_assistant_turn,
                    tool_hint_lang=options.tool_hint_lang,
                )
            )
            return not ctx.state.interrupted
        ctx.messages, should_continue = self._handle_final_response_iteration(
            response=response,
            messages=ctx.messages,
            current_task_ref=ctx.current_task_ref,
            artifact_session_key=options.artifact_session_key,
            state=ctx.state,
        )
        return should_continue

    async def _run_agent_loop(
        self,
        initial_messages: list[dict[str, Any]],
        *,
        options: RunAgentLoopOptions | None = None,
    ) -> tuple[Any, ...]:
        run_options = options or RunAgentLoopOptions()
        ctx = build_run_loop_context(
            self,
            initial_messages=initial_messages,
            options=run_options,
        )
        while ctx.state.iteration < self.max_iterations:
            ctx.state.iteration += 1
            iteration_result = await self._prepare_run_loop_iteration(
                initial_messages=initial_messages,
                ctx=ctx,
                options=run_options,
            )
            if iteration_result is None:
                break
            response, tool_exposure = iteration_result
            should_continue = await self._handle_run_loop_response(
                response=response,
                tool_exposure=tool_exposure,
                initial_messages=initial_messages,
                ctx=ctx,
                options=run_options,
            )
            if ctx.state.interrupted or not should_continue:
                break
        return await self._finalize_run_loop(ctx=ctx, options=run_options)

    async def _finalize_run_loop(
        self,
        *,
        ctx: RunLoopContext,
        options: RunAgentLoopOptions,
    ) -> tuple[Any, ...]:
        self._finalize_tool_observability(
            FinalizeToolObservabilityRequest(
                tool_budget=ctx.tool_budget,
                counters=ctx.counters,
                tools_used=ctx.tools_used,
                total_errors=ctx.state.total_errors,
                last_tool_exposure=ctx.last_tool_exposure,
            )
        )
        await archive_run_artifact(
            self,
            ArchiveRunArtifactRequest(
                artifact_store=ctx.artifact_store,
                artifact_session_key=options.artifact_session_key,
                started_at=ctx.started_at,
                user_request=ctx.user_request,
                tool_signal_text=options.tool_signal_text,
                state=ctx.state,
                tools_used=ctx.tools_used,
                tool_trace=ctx.tool_trace,
                reasoning_snippets=ctx.reasoning_snippets,
                tool_exposure_history=ctx.tool_exposure_history,
                provider_finish_reason=ctx.provider_finish_reason,
            ),
        )
        return build_run_loop_result(
            ctx=ctx,
            return_interrupt=options.return_interrupt,
        )
