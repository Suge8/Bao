from __future__ import annotations

from typing import Any

from bao.agent.tool_result import ToolResultValue
from bao.agent.tools._coding_agent_cache import MAX_TOOL_TIMEOUT_SECONDS
from bao.agent.tools._coding_agent_payloads import (
    ErrorPayloadRequest,
    FailurePayloadRequest,
    SuccessPayloadRequest,
    error_response,
    failure_response,
    success_response,
)
from bao.agent.tools._coding_agent_response import (
    build_details_hint,
    render_payload,
    summarize_output,
    timeout_error_guidance,
    timeout_retry_hint,
    transient_retry_hint,
    trim_for_summary,
)


class CodingAgentResponseMixin:
    def _success_response(self, request: SuccessPayloadRequest) -> ToolResultValue:
        payload_request = SuccessPayloadRequest(
            tool_label=self._tool_label,
            request_id=request.request_id,
            context_key=request.context_key,
            active_session=request.active_session,
            resolved_session=request.resolved_session,
            model=request.model,
            timeout=request.timeout,
            cwd=str(request.cwd),
            attempts=request.attempts,
            duration_ms=request.duration_ms,
            command_preview=request.command_preview,
            final_output=request.final_output,
            detail_stdout=request.detail_stdout,
            stderr_text=request.stderr_text,
            max_output_chars=request.max_output_chars,
            include_details=request.include_details,
            response_format=request.response_format,
            extra_payload_fields=self._extra_payload_fields(request.extra_payload_fields),
            extra_meta_fields=self._extra_meta_fields({}),
            details_hint=self._build_details_hint(
                request_id=request.request_id,
                session_id=request.active_session,
                include_details=request.include_details,
                details_available=bool(request.final_output.strip() or request.stderr_text.strip()),
            ),
            meta_prefix=self._meta_prefix,
        )
        return success_response(payload_request, self.detail_cache)

    def _timeout_error_guidance(self, timeout_seconds: int) -> str:
        return timeout_error_guidance(timeout_seconds, MAX_TOOL_TIMEOUT_SECONDS)

    def _timeout_retry_hint(self, timeout_seconds: int) -> str:
        return timeout_retry_hint(timeout_seconds, MAX_TOOL_TIMEOUT_SECONDS)

    def _transient_retry_hint(self, timeout_seconds: int) -> str:
        return transient_retry_hint(timeout_seconds, MAX_TOOL_TIMEOUT_SECONDS)

    def _error_response(self, request: ErrorPayloadRequest) -> ToolResultValue:
        payload_request = ErrorPayloadRequest(
            status=request.status,
            message=request.message,
            project_path=request.project_path,
            timeout_seconds=request.timeout_seconds,
            used_session_id=request.used_session_id,
            continued=request.continued,
            model=request.model,
            attempts=request.attempts,
            duration_ms=request.duration_ms,
            exit_code=request.exit_code,
            summary=request.summary,
            error_type=request.error_type,
            request_id=request.request_id,
            context_key=request.context_key,
            command_preview=request.command_preview,
            response_format=request.response_format,
            extra_payload_fields=self._extra_payload_fields(request.extra_payload_fields),
            extra_meta_fields=self._extra_meta_fields({}),
            hints=request.hints,
            meta_prefix=self._meta_prefix,
        )
        return error_response(payload_request, self.detail_cache)

    def _failure_response(
        self,
        request: FailurePayloadRequest,
        *,
        stdout_text: str,
        stale_session_cleared: bool = False,
    ) -> ToolResultValue:
        out = stdout_text.strip()
        err = request.stderr_text.strip()
        hints = self._build_failure_hints(out, err)
        error_type = "stale_session" if stale_session_cleared else self._classify_error_type(out, err)
        if stale_session_cleared:
            hints.insert(
                0,
                f"Stored {self._tool_label} session expired and was cleared. Retry once to start a fresh session.",
            )
        if not hints and self._is_transient_failure(out, err):
            hints.append(self._transient_retry_hint(request.timeout_seconds))
        payload_request = FailurePayloadRequest(
            tool_label=self._tool_label,
            request_id=request.request_id,
            context_key=request.context_key,
            project_path=request.project_path,
            timeout_seconds=request.timeout_seconds,
            used_session_id=request.used_session_id,
            continued=request.continued,
            model=request.model,
            attempts=request.attempts,
            duration_ms=request.duration_ms,
            return_code=request.return_code,
            final_output=request.final_output,
            stderr_text=request.stderr_text,
            max_output_chars=request.max_output_chars,
            include_details=request.include_details,
            command_preview=request.command_preview,
            response_format=request.response_format,
            extra_payload_fields=self._extra_payload_fields(request.extra_payload_fields),
            extra_meta_fields=self._extra_meta_fields({}),
            hints=hints,
            error_type=error_type,
            stdout_for_cache=request.stdout_for_cache,
            details_hint=self._build_details_hint(
                request_id=request.request_id,
                session_id=request.used_session_id,
                include_details=request.include_details,
                details_available=bool(request.final_output or err),
            ),
            meta_prefix=self._meta_prefix,
        )
        return failure_response(payload_request, self.detail_cache)

    @staticmethod
    def _summarize_output(stdout_text: str, stderr_text: str, max_chars: int = 1600) -> str:
        return summarize_output(stdout_text, stderr_text, max_chars=max_chars)

    @staticmethod
    def _trim_for_summary(text: str, max_chars: int) -> str:
        return trim_for_summary(text, max_chars)

    def _build_details_hint(
        self,
        request_id: str,
        session_id: str | None,
        include_details: bool,
        details_available: bool,
    ) -> str | None:
        return build_details_hint(
            tool_name=self.name,
            request_id=request_id,
            session_id=session_id,
            include_details=include_details,
            details_available=details_available,
        )

    def _render_payload(self, payload: dict[str, Any], response_format: str) -> ToolResultValue:
        return render_payload(
            payload=payload,
            response_format=response_format,
            meta_prefix=self._meta_prefix,
            extra_meta_fields=self._extra_meta_fields(payload),
        )
