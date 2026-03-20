from __future__ import annotations

from typing import Any

from loguru import logger

from bao.agent import shared
from bao.agent.artifacts import ArtifactStore, apply_tool_output_budget
from bao.agent.artifacts_models import ToolOutputBudgetRequest
from bao.agent.protocol import ToolErrorCategory
from bao.agent.run_artifacts import RunArtifactPayloadRequest, build_run_artifact_payload
from bao.agent.tool_result import tool_result_payload

from ._subagent_types import (
    AnnounceResultRequest,
    ArchiveRunRequest,
    CodingProgressSetupRequest,
    DiagnosticRecord,
    FinalizeFailureRequest,
    FinalizeSuccessRequest,
    StatusUpdate,
    ToolCallExecutionRequest,
)


class _SubagentRunActionsMixin:
    def _archive_subagent_run_artifact(self, request: ArchiveRunRequest) -> None:
        try:
            diagnostics_snapshot = self._runtime_diagnostics.snapshot(
                max_events=12,
                max_log_lines=0,
                allowed_sources=["subagent"],
                allowed_session_keys=[request.task_id],
            )
            run_artifact = build_run_artifact_payload(
                RunArtifactPayloadRequest(
                    run_kind="subagent",
                    session_key=request.task_id,
                    model=self.model,
                    started_at=request.started_at,
                    finished_at=request.finished_at,
                    user_request=request.task,
                    tool_signal_text=None,
                    final_content=request.state.final_content,
                    exit_reason=request.exit_reason,
                    provider_finish_reason=request.provider_finish_reason,
                    provider_error=request.state.provider_error,
                    interrupted=request.state.interrupted,
                    total_errors=request.state.total_errors,
                    tools_used=request.tools_used,
                    tool_trace=request.tool_trace,
                    reasoning_snippets=request.reasoning_snippets,
                    last_state_text=request.state.last_state_text,
                    tool_exposure_history=request.tool_exposure_history,
                    tool_observability={},
                    diagnostics_snapshot=diagnostics_snapshot,
                )
            )
            store = request.artifact_store or ArtifactStore(
                self.workspace,
                f"subagent_{request.task_id}",
                self._artifact_retention_days,
            )
            _ = store.archive_json("trajectory", "subagent_run", run_artifact)
        except Exception as exc:
            logger.debug("subagent run artifact archive failed: {}", exc)

    async def _execute_tool_call_block(self, request: ToolCallExecutionRequest) -> None:
        self._mark_tool_execution_start(request)
        progress_backend = self._setup_coding_progress_callback(
            CodingProgressSetupRequest(
                task_id=request.task_id,
                tool_call=request.tool_call,
                coding_tool=request.coding_tool,
                tool_step=request.state.total_tool_steps_for_sufficiency,
            )
        )
        raw_result = await self._execute_tool(request, progress_backend)
        result = self._append_tool_result_message(request, raw_result)
        self._record_tool_trace(request, raw_result=raw_result, result=result)
        self._handle_tool_error_state(request, raw_result)

    def _mark_tool_execution_start(self, request: ToolCallExecutionRequest) -> None:
        action_preview = shared.summarize_tool_args_for_trace(
            request.tool_call.name,
            request.tool_call.arguments,
            max_len=50,
        )
        self._update_status(
            StatusUpdate(
                task_id=request.task_id,
                phase=f"tool:{request.tool_call.name}",
                tool_steps=request.state.total_tool_steps_for_sufficiency + 1,
                action=f"{request.tool_call.name}({action_preview})",
            )
        )
        logger.debug(
            "Subagent [{}] executing: {} with arguments: {}",
            request.task_id,
            request.tool_call.name,
            self._redact_tool_args_for_log(request.tool_call.name, request.tool_call.arguments),
        )

    async def _execute_tool(self, request: ToolCallExecutionRequest, progress_backend: Any) -> Any:
        try:
            return await request.tools.execute(
                request.tool_call.name,
                request.tool_call.arguments,
                raw_arguments=request.tool_call.raw_arguments,
                argument_parse_error=request.tool_call.argument_parse_error,
            )
        finally:
            if progress_backend and hasattr(progress_backend, "set_progress_callback"):
                progress_backend.set_progress_callback(None)

    def _append_tool_result_message(self, request: ToolCallExecutionRequest, raw_result: Any) -> str:
        result, budget_event = apply_tool_output_budget(
            ToolOutputBudgetRequest(
                store=request.artifact_store,
                tool_name=request.tool_call.name,
                tool_call_id=request.tool_call.id,
                result=tool_result_payload(raw_result),
                offload_chars=self._tool_offload_chars,
                preview_chars=self._tool_preview_chars,
                hard_chars=self._tool_hard_chars,
                ctx_mgmt=self._ctx_mgmt,
            )
        )
        self._accumulate_budget(
            request.task_id,
            offloaded_chars=budget_event.offloaded_chars,
            clipped_chars=budget_event.hard_clipped_chars,
        )
        result, screenshot_image_b64 = self._handle_screenshot_marker(request.tool_call.name, result)
        tool_message: dict[str, Any] = {
            "role": "tool",
            "tool_call_id": request.tool_call.id,
            "name": request.tool_call.name,
            "content": result,
        }
        if screenshot_image_b64:
            tool_message["_image"] = screenshot_image_b64
        request.messages.append(tool_message)
        return result

    def _record_tool_trace(
        self,
        request: ToolCallExecutionRequest,
        *,
        raw_result: Any,
        result: str,
    ) -> None:
        error_info = self._parse_tool_error(request.tool_call.name, raw_result)
        trace_entry = shared.build_tool_trace_entry(
            shared.ToolTraceEntryRequest(
                trace_idx=len(request.tool_trace) + 1,
                tool_name=request.tool_call.name,
                args_preview=shared.summarize_tool_args_for_trace(
                    request.tool_call.name,
                    request.tool_call.arguments,
                ),
                has_error=bool(error_info and error_info.is_error),
                result=result,
            )
        )
        request.tool_trace.append(trace_entry)
        request.sufficiency_trace.append(trace_entry)
        if len(request.sufficiency_trace) > 32:
            del request.sufficiency_trace[:-32]
        request.state.total_tool_steps_for_sufficiency += 1

    def _handle_tool_error_state(self, request: ToolCallExecutionRequest, raw_result: Any) -> None:
        error_info = self._parse_tool_error(request.tool_call.name, raw_result)
        if error_info and error_info.is_error:
            self._record_failed_tool(request, error_info)
            return
        if error_info and error_info.category == ToolErrorCategory.INTERRUPTED:
            request.state.consecutive_errors = 0
            return
        request.state.consecutive_errors = 0

    def _record_failed_tool(self, request: ToolCallExecutionRequest, error_info: Any) -> None:
        request.state.total_errors += 1
        request.state.consecutive_errors += 1
        failed_preview = shared.summarize_tool_args_for_trace(
            request.tool_call.name,
            request.tool_call.arguments,
            max_len=60,
        )
        shared.push_failed_direction(
            request.failed_directions,
            f"{request.tool_call.name}({failed_preview})",
        )
        status = self._task_statuses.get(request.task_id)
        task_label = status.label if status else ""
        if status:
            status.last_error_category = error_info.category
            status.last_error_code = error_info.code
            status.last_error_message = self._sanitize_visible(
                error_info.message or error_info.category
            )
        self._record_runtime_diagnostic(
            DiagnosticRecord(
                stage="tool_call",
                message=error_info.message,
                code=error_info.code or error_info.category,
                retryable=error_info.retryable,
                task_id=request.task_id,
                label=task_label,
                details={
                    "tool_name": request.tool_call.name,
                    "excerpt": error_info.raw_excerpt,
                },
            )
        )

    async def _finalize_subagent_success(self, request: FinalizeSuccessRequest) -> None:
        final_result = request.final_result or "Task completed but no final response was generated."
        self._update_status(
            StatusUpdate(
                task_id=request.task_id,
                phase="completed",
                status="completed",
                iteration=request.iteration,
                tool_steps=request.tool_step,
                result_summary=final_result[:500],
            )
        )
        self._persist_child_status(
            task_id=request.task_id,
            label=request.label,
            origin=request.origin,
            result=final_result,
            status="completed",
        )
        logger.info("✅ 子代完成 / subagent done: [{}]", request.task_id)
        await self._announce_result_non_fatal(
            AnnounceResultRequest(
                task_id=request.task_id,
                label=request.label,
                task=request.task,
                result=final_result,
                origin=request.origin,
                status="ok",
            )
        )

    async def _finalize_subagent_failure(self, request: FinalizeFailureRequest) -> None:
        error_message = f"Error: {request.error}"
        self._update_status(
            StatusUpdate(
                task_id=request.task_id,
                status="failed",
                phase="failed",
                result_summary=error_message[:500],
            )
        )
        self._persist_child_status(
            task_id=request.task_id,
            label=request.label,
            origin=request.origin,
            result=error_message,
            status="failed",
        )
        status = self._task_statuses.get(request.task_id)
        self._record_runtime_diagnostic(
            DiagnosticRecord(
                stage="failed",
                message=error_message,
                code=status.last_error_code if status and status.last_error_code else "subagent_failed",
                retryable=False,
                task_id=request.task_id,
                label=request.label,
                details={
                    "task": self._sanitize_visible(request.task[:200]),
                    "last_error_category": status.last_error_category if status else None,
                    "last_error_message": status.last_error_message if status else None,
                },
            )
        )
        logger.error("❌ 子代失败 / subagent failed: [{}]: {}", request.task_id, request.error)
        await self._announce_result_non_fatal(
            AnnounceResultRequest(
                task_id=request.task_id,
                label=request.label,
                task=request.task,
                result=error_message,
                origin=request.origin,
                status="error",
            )
        )
