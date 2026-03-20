from __future__ import annotations

from typing import Any

from bao.agent import shared

from ._subagent_types import CodingProgressSetupRequest, PreIterationRequest, StatusUpdate


class _SubagentToolRuntimeMixin:
    async def _run_iteration_prechecks(self, request: PreIterationRequest):
        from bao.agent.run_controller import PreIterationCheckRequest, apply_pre_iteration_checks

        return await apply_pre_iteration_checks(
            PreIterationCheckRequest(
                messages=request.messages,
                initial_messages=request.initial_messages,
                user_request=request.task,
                artifact_store=request.artifact_store,
                state=request.state,
                tool_trace=request.tool_trace,
                reasoning_snippets=request.reasoning_snippets,
                failed_directions=request.failed_directions,
                sufficiency_trace=request.sufficiency_trace,
                ctx_mgmt=self._ctx_mgmt,
                compact_bytes=self._compact_bytes,
                compress_state=self._compress_state,
                check_sufficiency=self._check_sufficiency,
                compact_messages=self._compact_messages,
            )
        )

    async def _chat_subagent(
        self,
        messages: list[dict[str, Any]],
        tools,
        *,
        force_final_response: bool,
    ) -> Any:
        current_tools = [] if force_final_response else tools.get_budgeted_definitions()[0]
        return await shared.call_provider_chat(
            shared.ProviderChatRequest(
                provider=self.provider,
                request=shared.ChatRequest(
                    messages=messages,
                    tools=current_tools,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    reasoning_effort=self.reasoning_effort,
                    service_tier=self.service_tier,
                    source="subagent",
                ),
                patched_log_label="Subagent repaired",
            )
        )

    def _setup_coding_progress_callback(
        self, request: CodingProgressSetupRequest
    ) -> Any | None:
        if request.tool_call.name != "coding_agent":
            return None
        backend_name = request.tool_call.arguments.get("agent")
        if not isinstance(backend_name, str):
            return None
        backend = request.coding_tool._backends.get(backend_name)
        if not backend or not hasattr(backend, "set_progress_callback"):
            return None
        step_index = request.tool_step + 1

        async def _on_coding_progress(line: str) -> None:
            progress = self._normalize_progress_line(line)
            if not progress:
                return
            self._update_status(
                StatusUpdate(
                    task_id=request.task_id,
                    phase="tool:coding_agent",
                    tool_steps=step_index,
                    action=f"{backend_name}: {progress}",
                )
            )

        backend.set_progress_callback(_on_coding_progress)
        return backend

    def _handle_screenshot_marker(self, tool_name: str, result: str) -> tuple[str, str | None]:
        result_text, screenshot_image_b64 = shared.handle_screenshot_marker(
            shared.ScreenshotMarkerRequest(
                tool_name=tool_name,
                result=result,
                read_error_label="子代截图失败 / screenshot read failed",
                unsafe_path_label="子代忽略非安全截图路径 / ignored unsafe screenshot path",
            )
        )
        return str(result_text), screenshot_image_b64
