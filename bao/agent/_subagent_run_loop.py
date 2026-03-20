from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from loguru import logger

from bao.agent import shared
from bao.agent.artifacts import ArtifactStore
from bao.agent.run_controller import RunLoopState, build_error_feedback

from ._subagent_types import (
    ArchiveRunRequest,
    FinalizeFailureRequest,
    FinalizeSuccessRequest,
    PreIterationRequest,
    PrepareMessagesRequest,
    RunRequest,
    StatusUpdate,
    ToolCallExecutionRequest,
)


@dataclass
class _RunContext:
    request: RunRequest
    state: RunLoopState = field(default_factory=RunLoopState)
    artifact_store: ArtifactStore | None = None
    tool_trace: list[str] = field(default_factory=list)
    reasoning_snippets: list[str] = field(default_factory=list)
    sufficiency_trace: list[str] = field(default_factory=list)
    failed_directions: list[str] = field(default_factory=list)
    tool_exposure_history: list[Any] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    provider_finish_reason: str = ""
    exit_reason: str = "failed"
    started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    tools: Any = None
    coding_tool: Any = None
    max_iterations: int = 0
    messages: list[dict[str, Any]] = field(default_factory=list)
    initial_messages: list[dict[str, Any]] = field(default_factory=list)


class _SubagentRunLoopMixin:
    async def _run_subagent(self, request: RunRequest) -> None:
        logger.info("🚀 子代启动 / subagent start: [{}]: {}", request.task_id, request.label)
        context = _RunContext(request=request)
        try:
            context = await self._bootstrap_run_context(request)
            await self._execute_run_loop(context)
            await self._finalize_run_context(context)
        except asyncio.CancelledError:
            context.state.interrupted = True
            context.exit_reason = "cancelled"
            self._mark_cancelled(request)
            raise
        except Exception as exc:
            context.exit_reason = "failed"
            await self._finalize_subagent_failure(
                FinalizeFailureRequest(
                    task_id=request.task_id,
                    label=request.label,
                    task=request.task,
                    origin=request.origin,
                    error=exc,
                )
            )
        finally:
            self._archive_subagent_run_artifact(
                ArchiveRunRequest(
                    task_id=request.task_id,
                    task=request.task,
                    artifact_store=context.artifact_store,
                    started_at=context.started_at,
                    finished_at=datetime.now().isoformat(timespec="seconds"),
                    state=context.state,
                    tool_trace=context.tool_trace,
                    tools_used=context.tools_used,
                    reasoning_snippets=context.reasoning_snippets,
                    tool_exposure_history=context.tool_exposure_history,
                    provider_finish_reason=context.provider_finish_reason,
                    exit_reason=context.exit_reason,
                )
            )

    async def _bootstrap_run_context(self, request: RunRequest) -> _RunContext:
        context = _RunContext(request=request)
        self._persist_child_user_turn_if_needed(request)
        self._update_status(StatusUpdate(task_id=request.task_id, phase="preflighting"))
        setup = self._setup_subagent_tools(request.task_id, request.origin)
        coding_tools, coding_backend_issues = await self._resolve_coding_backends(
            request=request,
            coding_tool=setup.coding_tool,
            coding_tools=setup.coding_tools,
        )
        related_memory, related_experience = await self._get_related_memory(request.task)
        self._maybe_cleanup_stale_artifacts()
        context.tools = setup.tools
        context.coding_tool = setup.coding_tool
        context.max_iterations = self.max_iterations
        context.messages, context.initial_messages = self._prepare_subagent_messages(
            PrepareMessagesRequest(
                task_id=request.task_id,
                task=request.task,
                child_session_key=request.origin.get("child_session_key"),
                channel=request.origin.get("channel"),
                has_search=setup.has_search,
                has_browser=setup.has_browser,
                coding_tools=coding_tools,
                coding_backend_issues=coding_backend_issues,
                related_memory=related_memory,
                related_experience=related_experience,
                context_from=request.context_from,
            )
        )
        context.artifact_store = self._create_subagent_artifact_store(request.task_id)
        return context

    async def _execute_run_loop(self, context: _RunContext) -> None:
        while context.state.iteration < context.max_iterations:
            context.state.iteration += 1
            interrupted = await self._run_iteration(context)
            if interrupted:
                break

    async def _run_iteration(self, context: _RunContext) -> bool:
        context.messages = await self._run_iteration_prechecks(
            PreIterationRequest(
                task=context.request.task,
                messages=context.messages,
                initial_messages=context.initial_messages,
                artifact_store=context.artifact_store,
                tool_trace=context.tool_trace,
                sufficiency_trace=context.sufficiency_trace,
                reasoning_snippets=context.reasoning_snippets,
                failed_directions=context.failed_directions,
                state=context.state,
            )
        )
        if context.state.interrupted:
            context.exit_reason = "interrupted"
            return True
        self._update_status(
            StatusUpdate(
                task_id=context.request.task_id,
                iteration=context.state.iteration,
                phase="thinking",
            )
        )
        context.tool_exposure_history.append(
            self._build_subagent_tool_exposure_snapshot(
                task=context.request.task,
                tools=context.tools,
                force_final_response=context.state.force_final_response,
            )
        )
        response = await self._chat_subagent(
            context.messages,
            context.tools,
            force_final_response=context.state.force_final_response,
        )
        context.provider_finish_reason = str(response.finish_reason or "")
        return await self._handle_iteration_response(context, response)

    async def _handle_iteration_response(self, context: _RunContext, response: Any) -> bool:
        if response.finish_reason == "interrupted":
            context.state.interrupted = True
            context.exit_reason = "interrupted"
            return True
        if response.has_tool_calls:
            await self._handle_tool_response(context, response)
            return False
        self._handle_final_response(context, response)
        return context.exit_reason != ""

    async def _handle_tool_response(self, context: _RunContext, response: Any) -> None:
        clean = self._strip_think(response.content)
        if clean:
            context.reasoning_snippets.append(clean[:200])
        context.messages.append(
            {
                "role": "assistant",
                "content": clean or "",
                "tool_calls": [tool_call.to_openai_tool_call() for tool_call in response.tool_calls],
                "reasoning_content": response.reasoning_content,
                "thinking_blocks": response.thinking_blocks,
            }
        )
        for tool_call in response.tool_calls:
            context.tools_used.append(tool_call.name)
            await self._execute_tool_call_block(
                ToolCallExecutionRequest(
                    task_id=context.request.task_id,
                    tool_call=tool_call,
                    tools=context.tools,
                    coding_tool=context.coding_tool,
                    artifact_store=context.artifact_store,
                    messages=context.messages,
                    tool_trace=context.tool_trace,
                    sufficiency_trace=context.sufficiency_trace,
                    failed_directions=context.failed_directions,
                    state=context.state,
                )
            )
        self._append_progress_feedback(context)
        if context.state.iteration % self._PROGRESS_INTERVAL == 0:
            await self._push_milestone(
                context.request.task_id,
                context.request.label,
                context.state.iteration,
                context.max_iterations,
                context.request.origin,
            )

    def _append_progress_feedback(self, context: _RunContext) -> None:
        error_feedback = build_error_feedback(
            context.state.consecutive_errors,
            context.failed_directions,
        )
        if error_feedback:
            context.messages.append({"role": "user", "content": error_feedback})
            return
        if (
            context.state.total_tool_steps_for_sufficiency >= 8
            and context.state.total_tool_steps_for_sufficiency % 4 == 0
        ):
            context.messages.append(
                {
                    "role": "user",
                    "content": (
                        f"[Progress: {context.state.total_tool_steps_for_sufficiency} steps completed]"
                        " Focus on completing the task efficiently."
                    ),
                }
            )

    def _handle_final_response(self, context: _RunContext, response: Any) -> None:
        clean_final = self._strip_think(response.content)
        if response.finish_reason == "error":
            context.state.provider_error = True
            context.state.final_content = clean_final or "Error calling the AI model."
            context.exit_reason = "provider_error"
            return
        (
            context.state.force_final_response,
            context.state.force_final_backoff_used,
            retry_prompt,
        ) = shared.maybe_backoff_empty_final(
            force_final_response=context.state.force_final_response,
            force_final_backoff_used=context.state.force_final_backoff_used,
            clean_final=clean_final,
        )
        if retry_prompt is not None:
            context.messages.append(retry_prompt)
            context.exit_reason = ""
            return
        context.state.final_content = clean_final
        context.exit_reason = "completed" if clean_final is not None else "max_iterations"

    async def _finalize_run_context(self, context: _RunContext) -> None:
        if context.exit_reason == "provider_error":
            await self._finalize_subagent_failure(
                FinalizeFailureRequest(
                    task_id=context.request.task_id,
                    label=context.request.label,
                    task=context.request.task,
                    origin=context.request.origin,
                    error=RuntimeError(context.state.final_content or "Error calling the AI model."),
                )
            )
            return
        if context.exit_reason == "interrupted":
            self._mark_interrupted(context.request.task_id)
            return
        await self._finalize_subagent_success(
            FinalizeSuccessRequest(
                task_id=context.request.task_id,
                label=context.request.label,
                task=context.request.task,
                final_result=context.state.final_content,
                origin=context.request.origin,
                iteration=context.state.iteration,
                tool_step=context.state.total_tool_steps_for_sufficiency,
            )
        )
