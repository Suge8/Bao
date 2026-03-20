from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from loguru import logger

from bao.agent._loop_chat_turn import ChatOnceRequest
from bao.agent._loop_run_models import (
    ArchiveRunArtifactRequest,
    FinalizeToolObservabilityRequest,
    RunAgentLoopOptions,
    RunLoopContext,
)
from bao.agent._loop_types import ToolObservabilityCounters as _ToolObservabilityCounters
from bao.agent.run_artifacts import RunArtifactPayloadRequest, build_run_artifact_payload
from bao.agent.run_controller import RunLoopState


def finalize_tool_observability(loop: Any, request: FinalizeToolObservabilityRequest) -> None:
    loop._last_tool_budget = request.tool_budget
    counters = request.counters
    total_tool_calls = len(request.tools_used)
    tool_calls_error = max(
        0,
        total_tool_calls - counters.tool_calls_ok - counters.interrupted_tool_calls,
    )
    schema_bytes_avg = (
        counters.schema_bytes_total // counters.schema_samples
        if counters.schema_samples > 0
        else 0
    )
    tool_exposure = request.last_tool_exposure
    loop._last_tool_observability = {
        "schema_samples": counters.schema_samples,
        "schema_tool_count_last": counters.schema_tool_count_last,
        "schema_tool_count_max": counters.schema_tool_count_max,
        "schema_bytes_last": counters.schema_bytes_last,
        "schema_bytes_max": counters.schema_bytes_max,
        "schema_bytes_avg": schema_bytes_avg,
        "schema_tokens_est_last": loop._estimate_token_count(counters.schema_bytes_last),
        "tool_calls_total": total_tool_calls,
        "tool_calls_ok": counters.tool_calls_ok,
        "tool_calls_error": tool_calls_error,
        "invalid_parameter_errors": counters.invalid_parameter_errors,
        "tool_not_found_errors": counters.tool_not_found_errors,
        "execution_errors": counters.execution_errors,
        "interrupted_tool_calls": counters.interrupted_tool_calls,
        "total_errors": request.total_errors,
        "retry_rate_proxy": loop._safe_rate(counters.retry_attempts_proxy, total_tool_calls),
        "routing_mode": tool_exposure.mode if tool_exposure is not None else loop._tool_exposure_mode,
        "routing_full_exposure": bool(tool_exposure.full_exposure) if tool_exposure else False,
    }
    if tool_exposure is not None:
        loop._last_tool_observability["tool_exposure"] = tool_exposure.as_record()
    loop._runtime_diagnostics.set_tool_observability(loop._last_tool_observability)
    logger.debug("Tool observability summary: {}", loop._last_tool_observability)


def build_run_loop_context(
    loop: Any,
    *,
    initial_messages: list[dict[str, Any]],
    options: RunAgentLoopOptions,
) -> RunLoopContext:
    from bao.agent.artifacts import ArtifactStore

    artifact_store = (
        ArtifactStore(
            loop.state_root,
            options.artifact_session_key or "main_loop",
            loop._artifact_retention_days,
        )
        if loop._ctx_mgmt in ("auto", "aggressive")
        else None
    )
    user_request = next(
        (
            message["content"]
            for message in reversed(initial_messages)
            if message.get("role") == "user" and isinstance(message.get("content"), str)
        ),
        "",
    )
    return RunLoopContext(
        messages=list(initial_messages),
        state=RunLoopState(),
        tools_used=[],
        tool_trace=[],
        reasoning_snippets=[],
        completed_tool_msgs=[],
        reply_attachments=[],
        failed_directions=[],
        sufficiency_trace=[],
        current_task_ref=asyncio.current_task(),
        started_at=datetime.now().isoformat(timespec="seconds"),
        user_request=user_request,
        artifact_store=artifact_store,
        tool_budget={
            "offloaded_count": 0,
            "offloaded_chars": 0,
            "clipped_count": 0,
            "clipped_chars": 0,
        },
        counters=_ToolObservabilityCounters(),
    )


def build_chat_request(
    *,
    initial_messages: list[dict[str, Any]],
    ctx: RunLoopContext,
    options: RunAgentLoopOptions,
) -> ChatOnceRequest:
    return ChatOnceRequest(
        messages=ctx.messages,
        initial_messages=initial_messages,
        iteration=ctx.state.iteration,
        on_progress=options.on_progress,
        current_task_ref=ctx.current_task_ref,
        tool_signal_text=options.tool_signal_text,
        force_final_response=ctx.state.force_final_response,
        counters=ctx.counters,
        on_event=options.on_event,
    )


def build_run_loop_result(
    *,
    ctx: RunLoopContext,
    return_interrupt: bool,
) -> tuple[Any, ...]:
    if return_interrupt:
        return (
            ctx.state.final_content,
            ctx.tools_used,
            ctx.tool_trace,
            ctx.state.total_errors,
            ctx.reasoning_snippets,
            ctx.state.provider_error,
            ctx.state.interrupted,
            ctx.completed_tool_msgs,
            ctx.reply_attachments,
        )
    return (
        ctx.state.final_content,
        ctx.tools_used,
        ctx.tool_trace,
        ctx.state.total_errors,
        ctx.reasoning_snippets,
    )


async def archive_run_artifact(loop: Any, request: ArchiveRunArtifactRequest) -> None:
    from bao.agent.artifacts import ArtifactStore

    finished_at = datetime.now().isoformat(timespec="seconds")
    exit_reason = (
        "interrupted"
        if request.state.interrupted
        else "provider_error"
        if request.state.provider_error
        else "completed"
        if request.state.final_content is not None
        else "max_iterations"
    )
    try:
        diagnostics_snapshot = loop._runtime_diagnostics.snapshot(
            max_events=12,
            max_log_lines=0,
            allowed_session_keys=[request.artifact_session_key]
            if request.artifact_session_key
            else None,
        )
        run_artifact = build_run_artifact_payload(
            RunArtifactPayloadRequest(
                run_kind="agent_loop",
                session_key=request.artifact_session_key or "",
                model=loop.model,
                started_at=request.started_at,
                finished_at=finished_at,
                user_request=request.user_request,
                tool_signal_text=request.tool_signal_text,
                final_content=request.state.final_content,
                exit_reason=exit_reason,
                provider_finish_reason=request.provider_finish_reason,
                provider_error=request.state.provider_error,
                interrupted=request.state.interrupted,
                total_errors=request.state.total_errors,
                tools_used=request.tools_used,
                tool_trace=request.tool_trace,
                reasoning_snippets=request.reasoning_snippets,
                last_state_text=request.state.last_state_text,
                tool_exposure_history=request.tool_exposure_history,
                tool_observability=loop._last_tool_observability,
                diagnostics_snapshot=diagnostics_snapshot,
            )
        )
        archive_store = request.artifact_store or ArtifactStore(
            loop.state_root,
            request.artifact_session_key or "main_loop",
            loop._artifact_retention_days,
        )
        run_ref = archive_store.archive_json("trajectory", "agent_run", run_artifact)
        loop._last_tool_observability["run_artifact_ref"] = archive_store._workspace_relative(
            run_ref.path
        )
        loop._runtime_diagnostics.set_tool_observability(loop._last_tool_observability)
    except Exception as exc:
        logger.debug("run artifact archive failed: {}", exc)
