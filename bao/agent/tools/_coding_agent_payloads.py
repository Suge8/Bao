from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bao.agent.tool_result import ToolResultValue
from bao.agent.tools._coding_agent_cache import DetailCache, DetailRecordInput
from bao.agent.tools._coding_agent_response import (
    render_payload,
    summarize_output,
    trim_for_summary,
)


@dataclass(frozen=True)
class SuccessPayloadRequest:
    tool_label: str
    request_id: str
    context_key: str
    active_session: str | None
    resolved_session: str | None
    model: str | None
    timeout: int
    cwd: str
    attempts: int
    duration_ms: int
    command_preview: str
    final_output: str
    detail_stdout: str
    stderr_text: str
    max_output_chars: int
    include_details: bool
    response_format: str
    extra_payload_fields: dict[str, Any]
    extra_meta_fields: dict[str, Any] | None
    details_hint: str | None
    meta_prefix: str


@dataclass(frozen=True)
class ErrorPayloadRequest:
    status: str
    message: str
    project_path: str
    timeout_seconds: int
    used_session_id: str | None
    continued: bool
    model: str | None
    attempts: int
    duration_ms: int
    exit_code: int | None
    summary: str
    error_type: str
    request_id: str
    context_key: str
    command_preview: str
    response_format: str
    extra_payload_fields: dict[str, Any]
    extra_meta_fields: dict[str, Any] | None
    hints: list[str] | None
    meta_prefix: str


@dataclass(frozen=True)
class FailurePayloadRequest:
    tool_label: str
    request_id: str
    context_key: str
    project_path: str
    timeout_seconds: int
    used_session_id: str | None
    continued: bool
    model: str | None
    attempts: int
    duration_ms: int
    return_code: int
    final_output: str
    stderr_text: str
    max_output_chars: int
    include_details: bool
    command_preview: str
    response_format: str
    extra_payload_fields: dict[str, Any]
    extra_meta_fields: dict[str, Any] | None
    hints: list[str]
    error_type: str
    stdout_for_cache: str
    details_hint: str | None
    meta_prefix: str


def success_response(request: SuccessPayloadRequest, detail_cache: DetailCache) -> ToolResultValue:
    body = trim_for_summary(request.final_output, request.max_output_chars) or "(no output)"
    stderr_clean = request.stderr_text.strip()
    summary = summarize_output(body, stderr_clean)
    details_available = bool(body or stderr_clean)
    header = f"{request.tool_label} completed successfully."
    if request.active_session:
        header += f"\nSession: {request.active_session}"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "request_id": request.request_id,
        "status": "success",
        "message": header,
        "project_path": request.cwd,
        "timeout_seconds": request.timeout,
        "session_id": request.active_session,
        "continued": bool(request.resolved_session),
        "model": request.model,
        **request.extra_payload_fields,
        "attempts": request.attempts,
        "duration_ms": request.duration_ms,
        "exit_code": 0,
        "stdout": body if request.include_details else "",
        "stderr": stderr_clean if request.include_details else "",
        "summary": summary,
        "details_available": details_available,
        "details_hint": request.details_hint,
        "hints": [],
        "error_type": None,
        "command_preview": request.command_preview,
    }
    detail_cache.build_detail_record(
        DetailRecordInput(
            request_id=request.request_id,
            context_key=request.context_key,
            session_id=request.active_session,
            project_path=request.cwd,
            status="success",
            command_preview=request.command_preview,
            stdout=request.detail_stdout,
            stderr=request.stderr_text,
            summary=summary,
            attempts=request.attempts,
            duration_ms=request.duration_ms,
            exit_code=0,
        )
    )
    return render_payload(
        payload=payload,
        response_format=request.response_format,
        meta_prefix=request.meta_prefix,
        extra_meta_fields=request.extra_meta_fields,
    )


def error_response(request: ErrorPayloadRequest, detail_cache: DetailCache) -> ToolResultValue:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "request_id": request.request_id,
        "status": request.status,
        "message": request.message,
        "project_path": request.project_path,
        "timeout_seconds": request.timeout_seconds,
        "session_id": request.used_session_id,
        "continued": request.continued,
        "model": request.model,
        **request.extra_payload_fields,
        "attempts": request.attempts,
        "duration_ms": request.duration_ms,
        "exit_code": request.exit_code,
        "stdout": "",
        "stderr": "",
        "summary": request.summary,
        "details_available": False,
        "details_hint": None,
        "hints": request.hints or [],
        "error_type": request.error_type,
        "command_preview": request.command_preview,
    }
    detail_cache.build_detail_record(
        DetailRecordInput(
            request_id=request.request_id,
            context_key=request.context_key,
            session_id=request.used_session_id,
            project_path=request.project_path,
            status=request.status,
            command_preview=request.command_preview,
            stdout="",
            stderr="",
            summary=request.summary,
            attempts=request.attempts,
            duration_ms=request.duration_ms,
            exit_code=request.exit_code,
        )
    )
    return render_payload(
        payload=payload,
        response_format=request.response_format,
        meta_prefix=request.meta_prefix,
        extra_meta_fields=request.extra_meta_fields,
    )


def failure_response(request: FailurePayloadRequest, detail_cache: DetailCache) -> ToolResultValue:
    err = request.stderr_text.strip()
    summary = summarize_output(request.final_output, err)
    details_available = bool(request.final_output or err)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "request_id": request.request_id,
        "status": "error",
        "message": f"Error: {request.tool_label} failed (exit code {request.return_code}).",
        "project_path": request.project_path,
        "timeout_seconds": request.timeout_seconds,
        "session_id": request.used_session_id,
        "continued": request.continued,
        "model": request.model,
        **request.extra_payload_fields,
        "attempts": request.attempts,
        "duration_ms": request.duration_ms,
        "exit_code": request.return_code,
        "stdout": request.final_output[: request.max_output_chars] if request.include_details else "",
        "stderr": err[: request.max_output_chars] if request.include_details else "",
        "summary": summary,
        "details_available": details_available,
        "details_hint": request.details_hint,
        "hints": request.hints,
        "error_type": request.error_type,
        "command_preview": request.command_preview,
    }
    detail_cache.build_detail_record(
        DetailRecordInput(
            request_id=request.request_id,
            context_key=request.context_key,
            session_id=request.used_session_id,
            project_path=request.project_path,
            status="error",
            command_preview=request.command_preview,
            stdout=request.stdout_for_cache,
            stderr=request.stderr_text,
            summary=summary,
            attempts=request.attempts,
            duration_ms=request.duration_ms,
            exit_code=request.return_code,
        )
    )
    return render_payload(
        payload=payload,
        response_format=request.response_format,
        meta_prefix=request.meta_prefix,
        extra_meta_fields=request.extra_meta_fields,
    )
