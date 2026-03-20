from __future__ import annotations

from bao.agent.tools._coding_agent_execute_models import (
    CommandOutcome,
    ExecuteRequest,
    TimeoutOutcome,
)
from bao.agent.tools._coding_agent_payloads import (
    ErrorPayloadRequest,
    FailurePayloadRequest,
    SuccessPayloadRequest,
)


def build_missing_binary_request(
    *,
    cli_binary: str,
    tool_label: str,
    workspace: str,
    request: ExecuteRequest,
) -> ErrorPayloadRequest:
    return ErrorPayloadRequest(
        status="error",
        message=(
            f"Error: `{cli_binary}` command not found. "
            f"Install {tool_label} first and ensure it is on PATH."
        ),
        project_path=workspace,
        timeout_seconds=request.timeout,
        used_session_id=None,
        continued=False,
        model=request.model,
        attempts=0,
        duration_ms=0,
        exit_code=None,
        summary=f"{tool_label} CLI is not installed or not in PATH.",
        error_type="missing_binary",
        request_id=request.request_id,
        context_key=request.context_key,
        command_preview="",
        response_format=request.response_format,
        extra_payload_fields=request.extra_params,
        extra_meta_fields=None,
        hints=None,
        meta_prefix="",
    )


def build_invalid_project_path_request(
    *,
    tool_label: str,
    workspace: str,
    request: ExecuteRequest,
    error: ValueError,
) -> ErrorPayloadRequest:
    del tool_label
    return ErrorPayloadRequest(
        status="error",
        message=f"Error: {error}",
        project_path=str(request.project_path or workspace),
        timeout_seconds=request.timeout,
        used_session_id=None,
        continued=False,
        model=request.model,
        attempts=0,
        duration_ms=0,
        exit_code=None,
        summary=f"Invalid project path: {request.project_path or workspace}",
        error_type="invalid_project_path",
        request_id=request.request_id,
        context_key=request.context_key,
        command_preview="",
        response_format=request.response_format,
        extra_payload_fields=request.extra_params,
        extra_meta_fields=None,
        hints=None,
        meta_prefix="",
    )


def build_timeout_error_request(
    *,
    tool_label: str,
    timeout_guidance: str,
    timeout_hint: str,
    outcome: TimeoutOutcome,
) -> ErrorPayloadRequest:
    return ErrorPayloadRequest(
        status="timeout",
        message=(
            f"Error: {tool_label} timed out after {outcome.request.timeout} seconds. "
            f"{timeout_guidance}"
        ),
        project_path=str(outcome.prepared.cwd),
        timeout_seconds=outcome.request.timeout,
        used_session_id=outcome.prepared.resolved_session,
        continued=bool(outcome.prepared.resolved_session),
        model=outcome.request.model,
        attempts=outcome.attempts,
        duration_ms=outcome.duration_ms,
        exit_code=None,
        summary=f"{tool_label} timed out after {outcome.request.timeout} seconds.",
        error_type="timeout",
        request_id=outcome.request.request_id,
        context_key=outcome.request.context_key,
        command_preview=outcome.command_preview,
        response_format=outcome.request.response_format,
        extra_payload_fields=outcome.request.extra_params,
        extra_meta_fields=None,
        hints=[timeout_hint],
        meta_prefix="",
    )


def build_failure_payload_request(
    *,
    tool_label: str,
    outcome: CommandOutcome,
) -> FailurePayloadRequest:
    return FailurePayloadRequest(
        tool_label=tool_label,
        request_id=outcome.request.request_id,
        context_key=outcome.request.context_key,
        project_path=str(outcome.prepared.cwd),
        timeout_seconds=outcome.request.timeout,
        used_session_id=outcome.prepared.resolved_session,
        continued=bool(outcome.prepared.resolved_session),
        model=outcome.request.model,
        attempts=outcome.attempts,
        duration_ms=outcome.duration_ms,
        return_code=int(outcome.return_code or -1),
        final_output=outcome.final_output,
        stderr_text=outcome.stderr_text,
        max_output_chars=outcome.request.max_output_chars,
        include_details=outcome.request.include_details,
        command_preview=outcome.command_preview,
        response_format=outcome.request.response_format,
        extra_payload_fields=outcome.request.extra_params,
        extra_meta_fields=None,
        hints=[],
        error_type="execution_failed",
        stdout_for_cache=outcome.detail_stdout,
        details_hint=None,
        meta_prefix="",
    )


def build_success_payload_request(
    *,
    tool_label: str,
    outcome: CommandOutcome,
    active_session: str | None,
) -> SuccessPayloadRequest:
    return SuccessPayloadRequest(
        tool_label=tool_label,
        request_id=outcome.request.request_id,
        context_key=outcome.request.context_key,
        active_session=active_session,
        resolved_session=outcome.prepared.resolved_session,
        model=outcome.request.model,
        timeout=outcome.request.timeout,
        cwd=str(outcome.prepared.cwd),
        attempts=outcome.attempts,
        duration_ms=outcome.duration_ms,
        command_preview=outcome.command_preview,
        final_output=outcome.final_output,
        detail_stdout=outcome.detail_stdout,
        stderr_text=outcome.stderr_text,
        max_output_chars=outcome.request.max_output_chars,
        include_details=outcome.request.include_details,
        response_format=outcome.request.response_format,
        extra_payload_fields=outcome.request.extra_params,
        extra_meta_fields=None,
        details_hint=None,
        meta_prefix="",
    )
