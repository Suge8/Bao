from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from bao.agent import shared
from bao.agent._loop_chat_turn import ChatOnceRequest
from bao.agent._loop_chat_turn import (
    chat_once_with_selected_tools as _chat_once_with_selected_tools_impl,
)
from bao.agent._loop_constants import TOOL_OBS_LAST_KEY as _TOOL_OBS_LAST_KEY
from bao.agent._loop_tool_runtime_models import LoopPreIterationRequest
from bao.agent._loop_types import ToolObservabilityCounters as _ToolObservabilityCounters
from bao.agent._loop_types import reply_attachment_name_hint as _reply_attachment_name_hint
from bao.agent.run_controller import (
    PreIterationCheckRequest,
    apply_pre_iteration_checks,
)
from bao.agent.tool_exposure import ToolExposureSnapshot
from bao.agent.tool_result import ToolExecutionResult, tool_reply_contribution
from bao.runtime_diagnostics_models import RuntimeEventRequest
from bao.utils.attachments import build_attachment_payload

if TYPE_CHECKING:
    from bao.agent.artifacts import ArtifactStore
    from bao.session.manager import Session


class LoopToolRuntimeMixin:
    _TOOL_INTERRUPT_POLL = 0.2
    _TOOL_CANCEL_TIMEOUT = 5.0

    async def _await_tool_with_interrupt(
        self,
        tool_task: asyncio.Task[object],
        current_task_ref: asyncio.Task[None] | None,
    ) -> object:
        if current_task_ref is None:
            return await tool_task
        try:
            while not tool_task.done():
                if self._session_runs.is_interrupted(current_task_ref):
                    if tool_task.done():
                        return await tool_task
                    tool_task.cancel()
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(tool_task),
                            timeout=self._TOOL_CANCEL_TIMEOUT,
                        )
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                    except Exception:
                        pass
                    if tool_task.done() and not tool_task.cancelled():
                        try:
                            return tool_task.result()
                        except Exception:
                            pass
                    return ToolExecutionResult.interrupted()
                try:
                    return await asyncio.wait_for(asyncio.shield(tool_task), timeout=self._TOOL_INTERRUPT_POLL)
                except asyncio.TimeoutError:
                    continue
            return await tool_task
        except asyncio.CancelledError:
            if not tool_task.done():
                tool_task.cancel()
                try:
                    await asyncio.wait_for(
                        asyncio.shield(tool_task),
                        timeout=self._TOOL_CANCEL_TIMEOUT,
                    )
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                except Exception:
                    pass
            raise

    @staticmethod
    def _estimate_payload_bytes(payload: Any) -> int:
        try:
            return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        except Exception:
            return 0

    @staticmethod
    def _estimate_token_count(byte_size: int) -> int:
        return 0 if byte_size <= 0 else (byte_size + 3) // 4

    @staticmethod
    def _safe_rate(numerator: int, denominator: int) -> float | None:
        return None if denominator <= 0 else round(numerator / denominator, 4)

    def _persist_tool_observability(
        self,
        session: Session,
        *,
        channel: str,
        session_key: str,
    ) -> None:
        if not self._last_tool_observability:
            return
        session.metadata[_TOOL_OBS_LAST_KEY] = {
            "timestamp": datetime.now().isoformat(),
            "channel": channel,
            "session_key": session_key,
            **self._last_tool_observability,
        }

    def _record_runtime_diagnostic(self, request: RuntimeEventRequest) -> None:
        self._runtime_diagnostics.record_event(request)

    def _is_soft_interrupted(self, current_task_ref: asyncio.Task[None] | None) -> bool:
        return self._session_runs.is_interrupted(current_task_ref)

    async def _apply_pre_iteration_checks(
        self,
        request: LoopPreIterationRequest,
    ) -> list[dict[str, Any]]:
        return await apply_pre_iteration_checks(
            PreIterationCheckRequest(
                messages=request.messages,
                initial_messages=request.initial_messages,
                user_request=request.user_request,
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
                is_interrupted=lambda: self._is_soft_interrupted(request.current_task_ref),
            )
        )

    def _sample_tool_schema_if_needed(
        self,
        *,
        current_tools: list[dict[str, Any]],
        iteration: int,
        counters: _ToolObservabilityCounters,
    ) -> None:
        if not current_tools or counters.schema_samples > 0:
            return
        current_schema_bytes = self._estimate_payload_bytes(current_tools)
        counters.schema_samples += 1
        counters.schema_tool_count_last = len(current_tools)
        counters.schema_tool_count_max = max(counters.schema_tool_count_max, counters.schema_tool_count_last)
        counters.schema_bytes_last = current_schema_bytes
        counters.schema_bytes_max = max(counters.schema_bytes_max, current_schema_bytes)
        counters.schema_bytes_total += current_schema_bytes
        logger.debug(
            "Tool schema payload: iteration={}, tools={}, bytes={}, est_tokens={}",
            iteration,
            counters.schema_tool_count_last,
            current_schema_bytes,
            self._estimate_token_count(current_schema_bytes),
        )

    async def _chat_once_with_selected_tools(
        self,
        request: ChatOnceRequest,
    ) -> tuple[Any, ToolExposureSnapshot]:
        return await _chat_once_with_selected_tools_impl(self, request)

    def _handle_screenshot_marker(
        self,
        tool_name: str,
        result: str | Any,
    ) -> tuple[str | Any, str | None]:
        return shared.handle_screenshot_marker(
            shared.ScreenshotMarkerRequest(
                tool_name=tool_name,
                result=result,
                read_error_label="截图读取失败 / screenshot read failed",
                unsafe_path_label="忽略非安全截图路径 / ignored unsafe screenshot path",
            )
        )

    def _archive_reply_attachments(
        self,
        *,
        tool_name: str,
        artifact_session_key: str | None,
        artifact_store: ArtifactStore | None,
        raw_result: Any,
    ) -> list[dict[str, Any]]:
        contribution = tool_reply_contribution(raw_result)
        if contribution is None or not contribution.attachments:
            return []
        if artifact_store is None:
            from bao.agent.artifacts import ArtifactStore

            artifact_store = ArtifactStore(self.state_root, artifact_session_key or "main_loop", self._artifact_retention_days)
        archived: list[dict[str, Any]] = []
        for attachment in contribution.attachments:
            try:
                source_path = Path(attachment.path).expanduser().resolve()
            except OSError:
                continue
            if not source_path.is_file():
                continue
            try:
                size = source_path.stat().st_size
            except OSError:
                continue
            ref = artifact_store.write_binary_file(
                "reply_media",
                _reply_attachment_name_hint(tool_name, attachment.name.strip() or source_path.name),
                source_path,
                size=size,
                move_source=attachment.cleanup,
            )
            payload = build_attachment_payload(ref.path)
            if not isinstance(payload, dict):
                continue
            if attachment.name.strip():
                payload["fileName"] = attachment.name.strip()
            if attachment.mime_type.strip():
                payload["mimeType"] = attachment.mime_type.strip()
                payload["isImage"] = attachment.mime_type.strip().startswith("image/")
            try:
                payload["path"] = str(ref.path.relative_to(self.workspace))
            except ValueError:
                payload["path"] = str(ref.path)
            payload["size"] = int(payload.get("sizeBytes") or size)
            archived.append(payload)
        return archived
