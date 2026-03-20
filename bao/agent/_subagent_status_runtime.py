from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from loguru import logger

from bao.agent import shared
from bao.bus.events import OutboundMessage
from bao.progress_scope import subagent_progress_scope
from bao.runtime_diagnostics_models import RuntimeEventRequest

from ._subagent_types import (
    _ANSI_ESCAPE_RE,
    _SUBAGENT_ERROR_KEYWORDS,
    DiagnosticRecord,
    StatusUpdate,
)


@dataclass(frozen=True, slots=True)
class ChildResultRequest:
    child_session_key: str
    parent_session_key: str
    label: str
    task_id: str
    result: str
    status: str


class _SubagentStatusRuntimeMixin:
    @staticmethod
    def _sanitize_visible(text: str) -> str:
        return shared.sanitize_visible_text(text)

    def _persist_child_user_turn(
        self,
        child_session_key: str,
        *,
        parent_session_key: str,
        label: str,
        task_id: str,
        task: str,
    ) -> None:
        if self.sessions is None:
            return
        session = self.sessions.get_or_create(child_session_key)
        session.metadata.update(self._child_session_metadata(parent_session_key, label))
        session.add_message("user", task)
        self.sessions.save(session)
        self.sessions.set_child_running(child_session_key, task_id)

    @staticmethod
    def _child_session_metadata(parent_session_key: str, label: str) -> dict[str, Any]:
        return {
            "title": label,
            "session_kind": "subagent_child",
            "read_only": True,
            "parent_session_key": parent_session_key,
            "task_label": label,
        }

    def _persist_child_result(self, request: ChildResultRequest) -> None:
        if self.sessions is None:
            return
        session = self.sessions.get_or_create(request.child_session_key)
        self.sessions.clear_child_running(request.child_session_key, emit_change=False)
        session.metadata.update(
            self._child_session_metadata(request.parent_session_key, request.label)
            | {
                "child_status": request.status,
                "last_result_summary": self._sanitize_visible(request.result),
            }
        )
        assistant_status = "done" if request.status == "completed" else "error"
        session.add_message("assistant", request.result, status=assistant_status)
        self.sessions.save(session)

    def _child_session_history(self, child_session_key: str) -> list[dict[str, Any]]:
        if self.sessions is None or not self.sessions.session_exists(child_session_key):
            return []
        session = self.sessions.get_or_create(child_session_key)
        history = session.get_history(max_messages=80)
        return [
            dict(message) for message in history if message.get("role") in {"user", "assistant"}
        ]

    @staticmethod
    def _redact_tool_args_for_log(tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "exec":
            redacted = dict(args)
            command = redacted.get("command")
            if isinstance(command, str):
                redacted["command"] = f"<redacted:{len(command)} chars>"
            return json.dumps(redacted, ensure_ascii=False)
        if tool_name not in {"write_file", "edit_file"}:
            return json.dumps(args, ensure_ascii=False)
        redacted = dict(args)
        for key in ("content", "old_text", "new_text"):
            value = redacted.get(key)
            if isinstance(value, str):
                redacted[key] = f"<redacted:{len(value)} chars>"
        return json.dumps(redacted, ensure_ascii=False)

    @classmethod
    def _normalize_progress_line(cls, text: str) -> str:
        cleaned = _ANSI_ESCAPE_RE.sub("", text)
        cleaned = cleaned.replace("\x1b", "")
        cleaned = cls._sanitize_visible(cleaned).strip()
        if len(cleaned) > 180:
            cleaned = cleaned[:177] + "..."
        return cleaned

    def _update_status(self, update: StatusUpdate) -> None:
        status = self._task_statuses.get(update.task_id)
        if not status:
            return
        if update.iteration is not None:
            status.iteration = update.iteration
        if update.phase is not None:
            status.phase = update.phase
        if update.tool_steps is not None:
            status.tool_steps = update.tool_steps
        if update.status is not None:
            status.status = update.status
        if update.result_summary is not None:
            status.result_summary = self._sanitize_visible(update.result_summary)
        if update.action is not None:
            status.recent_actions.append(self._sanitize_visible(update.action))
            if len(status.recent_actions) > self._MAX_RECENT_ACTIONS:
                status.recent_actions = status.recent_actions[-self._MAX_RECENT_ACTIONS :]
        status.updated_at = time.time()

    def _record_runtime_diagnostic(self, record: DiagnosticRecord) -> None:
        self._runtime_diagnostics.record_event(
            RuntimeEventRequest(
                source="subagent",
                stage=record.stage,
                message=record.message,
                code=record.code,
                retryable=record.retryable,
                session_key=record.task_id,
                details={
                    "task_id": record.task_id,
                    "label": self._sanitize_visible(record.label),
                    **(record.details or {}),
                },
            )
        )

    def _accumulate_budget(
        self, task_id: str, *, offloaded_chars: int = 0, clipped_chars: int = 0
    ) -> None:
        status = self._task_statuses.get(task_id)
        if not status:
            return
        if offloaded_chars > 0:
            status.offloaded_count += 1
            status.offloaded_chars += offloaded_chars
        if clipped_chars > 0:
            status.clipped_count += 1
            status.clipped_chars += clipped_chars
        status.updated_at = time.time()

    async def _push_milestone(
        self, task_id: str, label: str, iteration: int, max_iter: int, origin: dict[str, str]
    ) -> None:
        status = self._task_statuses.get(task_id)
        content = f"⏳ [{self._sanitize_visible(label)}] {iteration}/{max_iter}"
        if status:
            content += f", {status.tool_steps} tools"
            if status.phase.startswith("tool:"):
                content += f" — {status.phase}"
            if status.recent_actions:
                recent = status.recent_actions[-3:]
                content += "\n" + "\n".join(f"  → {self._sanitize_visible(item)}" for item in recent)
            if status.clipped_count or status.offloaded_count:
                content += (
                    f"\n  budget clip:{status.clipped_count}/{status.clipped_chars} "
                    f"offload:{status.offloaded_count}/{status.offloaded_chars}"
                )
        try:
            await self.bus.publish_outbound(
                OutboundMessage(
                    channel=origin["channel"],
                    chat_id=origin["chat_id"],
                    content=content,
                    metadata={
                        "_progress": True,
                        "_subagent_progress": True,
                        "_progress_scope": subagent_progress_scope(task_id),
                        "task_id": task_id,
                        "_stream_event_schema": 1,
                        "_stream_event_type": "task_status",
                        "_stream_event_payload": {
                            "iteration": iteration,
                            "tool_steps": status.tool_steps if status else 0,
                            "status": status.status if status else "running",
                            "phase": status.phase if status else "starting",
                        },
                    },
                )
            )
        except Exception:
            logger.debug("Subagent [{}] milestone push failed (non-fatal)", task_id)

    def _cleanup_completed(self) -> None:
        finished = [
            (task_id, status)
            for task_id, status in self._task_statuses.items()
            if status.status != "running"
        ]
        if len(finished) <= self._MAX_COMPLETED:
            return
        finished.sort(key=lambda item: item[1].updated_at)
        for task_id, _ in finished[: len(finished) - self._MAX_COMPLETED]:
            self._task_statuses.pop(task_id, None)

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        return shared.strip_think_tags(text)

    async def _call_experience_llm(self, system: str, prompt: str) -> dict[str, Any] | None:
        return await shared.call_experience_llm(
            shared.ExperienceLLMRequest(
                system=system,
                prompt=prompt,
                experience_mode=self._experience_mode,
                provider=self.provider,
                model=self.model,
                utility_provider=self._utility_provider,
                utility_model=self._utility_model,
                service_tier=self.service_tier,
            )
        )

    @staticmethod
    def _has_tool_error(tool_name: str, result: object) -> bool:
        return shared.has_tool_error(tool_name, result, _SUBAGENT_ERROR_KEYWORDS)

    @staticmethod
    def _parse_tool_error(tool_name: str, result: object):
        return shared.parse_tool_error(tool_name, result, _SUBAGENT_ERROR_KEYWORDS)
