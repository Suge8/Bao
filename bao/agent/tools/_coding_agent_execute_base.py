from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from bao.agent.tool_result import ToolResultValue
from bao.agent.tools._coding_agent_cache import MAX_TOOL_TIMEOUT_SECONDS, MIN_TOOL_TIMEOUT_SECONDS
from bao.agent.tools._coding_agent_execute_models import (
    CommandOutcome,
    ExecuteRequest,
    PreparedExecuteRequest,
    TimeoutOutcome,
)
from bao.agent.tools._coding_agent_execute_requests import (
    build_failure_payload_request,
    build_invalid_project_path_request,
    build_missing_binary_request,
    build_success_payload_request,
    build_timeout_error_request,
)


class CodingAgentExecuteMixin:
    async def execute(self, **kwargs: Any) -> ToolResultValue:
        from bao.agent.tools import coding_agent_base as base_module

        request, error = self._build_execute_request(kwargs)
        if error:
            return error
        if request is None:
            return "Error: invalid options"

        if not base_module.shutil.which(self.cli_binary):
            return self._error_response(
                build_missing_binary_request(
                    cli_binary=self.cli_binary,
                    tool_label=self._tool_label,
                    workspace=str(self.workspace),
                    request=request,
                )
            )

        try:
            cwd = self._resolve_project_path(request.project_path)
        except ValueError as exc:
            return self._error_response(
                build_invalid_project_path_request(
                    tool_label=self._tool_label,
                    workspace=str(self.workspace),
                    request=request,
                    error=exc,
                )
            )

        prepared = await self._prepare_execute_request(request, cwd)
        return await self._execute_prepared_request(prepared)

    def _build_execute_request(
        self, kwargs: dict[str, Any]
    ) -> tuple[ExecuteRequest | None, ToolResultValue | None]:
        options, option_error = self._parse_execute_options(kwargs)
        if option_error:
            return None, option_error
        if options is None:
            return None, None
        extra_err = self._validate_extra_params(kwargs)
        if extra_err:
            return None, extra_err
        timeout = max(
            MIN_TOOL_TIMEOUT_SECONDS,
            min(int(options["timeout_raw"] or self.default_timeout_seconds), MAX_TOOL_TIMEOUT_SECONDS),
        )
        return (
            ExecuteRequest(
                prompt_text=options["prompt_text"],
                project_path=options["project_path"],
                session_id=options["session_id"],
                continue_session=options["continue_session"],
                model=options["model"],
                timeout=timeout,
                response_format=options["response_format"],
                max_output_chars=options["max_output_chars"],
                include_details=options["include_details"],
                extra_params=options["extra_params"],
                request_id=uuid.uuid4().hex,
                context_key=self._context_key.get(),
            ),
            None,
        )

    async def _prepare_execute_request(
        self, request: ExecuteRequest, cwd: Path
    ) -> PreparedExecuteRequest:
        extra_params = await self._prepare_extra_params(
            cwd=cwd,
            timeout=request.timeout,
            extra_params=request.extra_params,
        )
        resolved_session, session_source = await self._resolve_session_for_execute(
            explicit_session_id=request.session_id,
            continue_session=request.continue_session,
            context_key=request.context_key,
        )
        return PreparedExecuteRequest(
            request=ExecuteRequest(
                **{**request.__dict__, "extra_params": extra_params},
            ),
            cwd=cwd,
            resolved_session=resolved_session,
            session_source=session_source,
        )

    async def _execute_prepared_request(self, prepared: PreparedExecuteRequest) -> ToolResultValue:
        request = prepared.request
        exec_state: dict[str, Any] = {}
        try:
            cmd, exec_state = self._build_command(
                prompt=request.prompt_text,
                resolved_session=prepared.resolved_session,
                model=request.model,
                context_key=request.context_key,
                extra_params=request.extra_params,
            )
            command_preview = self._build_command_preview(cmd, request.prompt_text)
            result, attempts, duration_ms = await self._run_command_once(
                cmd=cmd,
                cwd=prepared.cwd,
                timeout=request.timeout,
            )
            if result["timed_out"]:
                return self._error_response(
                    build_timeout_error_request(
                        tool_label=self._tool_label,
                        timeout_guidance=self._timeout_error_guidance(request.timeout),
                        timeout_hint=self._timeout_retry_hint(request.timeout),
                        outcome=TimeoutOutcome(
                            request=request,
                            prepared=prepared,
                            command_preview=command_preview,
                            attempts=attempts,
                            duration_ms=duration_ms,
                        ),
                    )
                )
            return await self._handle_command_result(
                outcome=CommandOutcome(
                    request=request,
                    prepared=prepared,
                    command_preview=command_preview,
                    attempts=attempts,
                    duration_ms=duration_ms,
                    stdout_text=result["stdout"],
                    stderr_text=result["stderr"],
                    final_output="",
                    detail_stdout="",
                    return_code=result["returncode"],
                ),
                exec_state=exec_state,
            )
        finally:
            self._cleanup(exec_state)

    async def _handle_command_result(
        self,
        *,
        outcome: CommandOutcome,
        exec_state: dict[str, Any],
    ) -> ToolResultValue:
        exec_state["_returncode"] = outcome.return_code
        final_output = await self._extract_output(
            stdout_text=outcome.stdout_text,
            exec_state=exec_state,
        )
        detail_stdout = self._detail_stdout_for_cache(
            final_output=final_output,
            stdout_text=outcome.stdout_text,
            exec_state=exec_state,
        )
        hydrated_outcome = CommandOutcome(
            request=outcome.request,
            prepared=outcome.prepared,
            command_preview=outcome.command_preview,
            attempts=outcome.attempts,
            duration_ms=outcome.duration_ms,
            stdout_text=outcome.stdout_text,
            stderr_text=outcome.stderr_text,
            final_output=final_output,
            detail_stdout=detail_stdout,
            return_code=outcome.return_code,
        )
        if hydrated_outcome.return_code is None or hydrated_outcome.return_code != 0:
            return await self._handle_failed_result(hydrated_outcome)
        return await self._handle_success_result(hydrated_outcome, exec_state=exec_state)

    async def _handle_failed_result(self, outcome: CommandOutcome) -> ToolResultValue:
        stale_session = self._is_stale_session_error(outcome.stdout_text, outcome.stderr_text)
        stale_session_cleared = stale_session and outcome.prepared.session_source == "stored"
        if stale_session_cleared:
            await self._publish_session_event(
                context_key=outcome.request.context_key,
                session_id=outcome.prepared.resolved_session,
                action="cleared",
                reason="stale_session",
            )
        return self._failure_response(
            build_failure_payload_request(tool_label=self._tool_label, outcome=outcome),
            stdout_text=outcome.stdout_text,
            stale_session_cleared=stale_session_cleared,
        )

    async def _handle_success_result(
        self,
        outcome: CommandOutcome,
        *,
        exec_state: dict[str, Any],
    ) -> ToolResultValue:
        active_session = await self._resolve_session_after_success(
            stdout_text=outcome.stdout_text,
            resolved_session=outcome.prepared.resolved_session,
            cwd=outcome.prepared.cwd,
            exec_state=exec_state,
            timeout=outcome.request.timeout,
        )
        await self._publish_session_event(
            context_key=outcome.request.context_key,
            session_id=active_session,
            action="active",
        )
        return self._success_response(
            build_success_payload_request(
                tool_label=self._tool_label,
                outcome=outcome,
                active_session=active_session,
            )
        )
