from __future__ import annotations

import asyncio
import time
import uuid

from loguru import logger

from ._subagent_types import RunRequest, SpawnIssue, SpawnRequest, SpawnResult, TaskStatus

_NEW_TASK_HINT = "For a new subagent task, omit child_session_key."
_CONTINUE_CHILD_HINT = (
    "To continue an existing child thread, reuse an exact key from child-session notes or "
    "check_tasks_json."
)
_PROGRESS_HINT = "Query progress with task.task_id."


class _SubagentStatusSpawnMixin:
    async def spawn(self, request: SpawnRequest) -> SpawnResult:
        task_id = self._new_task_id()
        safe_label = self._safe_label(request.label or request.task or "unnamed task")
        origin = self._build_origin(request, task_id)
        child_key_error = self._validate_explicit_child_session_key(
            parent_session_key=request.session_key,
            child_session_key=request.child_session_key,
        )
        if child_key_error:
            return SpawnResult.failed(code=child_key_error.code, message=child_key_error.message)
        resume_context, warning = self._resolve_resume_context(request.context_from)
        self._task_statuses[task_id] = TaskStatus(
            task_id=task_id,
            child_session_key=origin.get("child_session_key"),
            label=safe_label,
            task_description=request.task[:200],
            origin=origin,
            max_iterations=self.max_iterations,
            resume_context=resume_context,
        )
        self._cleanup_completed()
        bg_task = asyncio.create_task(
            self._run_subagent(
                RunRequest(
                    task_id=task_id,
                    task=request.task,
                    label=safe_label,
                    origin=origin,
                    context_from=request.context_from,
                )
            )
        )
        self._running_tasks[task_id] = bg_task
        if request.session_key:
            self._session_tasks.setdefault(request.session_key, set()).add(task_id)
        bg_task.add_done_callback(
            lambda _: self._cleanup_running_task(task_id, session_key=request.session_key)
        )
        logger.info("🚀 启动子代 / subagent spawned: [{}]: {}", task_id, safe_label)
        return SpawnResult.spawned(
            task_id=task_id,
            label=safe_label,
            child_session_key=origin.get("child_session_key"),
            warning=warning,
        )

    def get_task_status(self, task_id: str) -> TaskStatus | None:
        return self._task_statuses.get(task_id)

    def get_all_statuses(self) -> list[TaskStatus]:
        return list(self._task_statuses.values())

    def get_running_count(self) -> int:
        return len(self._running_tasks)

    async def _cancel_by_session(self, session_key: str, *, wait: bool) -> int:
        task_ids = list(self._session_tasks.get(session_key, []))
        tasks = [
            self._running_tasks[task_id]
            for task_id in task_ids
            if task_id in self._running_tasks and not self._running_tasks[task_id].done()
        ]
        for task in tasks:
            task.cancel()
        if wait and tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return len(tasks)

    async def cancel_by_session(self, session_key: str, *, wait: bool = True) -> int:
        return await self._cancel_by_session(session_key, wait=wait)

    async def cancel_task(self, task_id: str) -> str:
        task = self._running_tasks.get(task_id)
        if not task:
            return f"No running task with id '{task_id}'."
        status = self._task_statuses.get(task_id)
        if task.done() or (status and status.status == "cancelled"):
            resolved = status.status if status else "finished"
            return f"Task '{task_id}' is already {resolved}."
        task.cancel()
        if status and status.status == "running":
            status.phase = "cancel_requested"
            status.updated_at = time.time()
        logger.info("👋 取消子代请求 / subagent cancel requested: [{}]", task_id)
        return f"Cancellation requested for task '{task_id}'."

    def _new_task_id(self) -> str:
        task_id = uuid.uuid4().hex[:12]
        while task_id in self._task_statuses or task_id in self._running_tasks:
            task_id = uuid.uuid4().hex[:12]
        return task_id

    def _safe_label(self, text: str) -> str:
        safe_label = self._sanitize_visible(text).replace('"', "'")
        if len(safe_label) > 48:
            return safe_label[:48] + "…"
        return safe_label

    def _build_origin(self, request: SpawnRequest, task_id: str) -> dict[str, str]:
        origin = {
            "channel": request.origin_channel,
            "chat_id": request.origin_chat_id,
        }
        if request.session_key:
            origin["session_key"] = request.session_key
        resolved_child_session_key = self._resolve_child_session_key(
            parent_session_key=request.session_key,
            child_session_key=request.child_session_key,
            lineage_id=task_id,
        )
        if resolved_child_session_key:
            origin["child_session_key"] = resolved_child_session_key
        return origin

    def _cleanup_running_task(self, task_id: str, *, session_key: str | None) -> None:
        self._running_tasks.pop(task_id, None)
        if session_key and (ids := self._session_tasks.get(session_key)):
            ids.discard(task_id)
            if not ids:
                self._session_tasks.pop(session_key, None)

    @staticmethod
    def _build_resume_context(context_from: str, prev: TaskStatus) -> str:
        return (
            f"[Continuing from previous task ({context_from})]\n"
            f"Previous task: {prev.task_description[:200]}\n"
            f"Previous result: {prev.result_summary or 'no summary'}"
        )

    def _resolve_resume_context(
        self, context_from: str | None
    ) -> tuple[str | None, SpawnIssue | None]:
        if not context_from:
            return None, None
        prev = self.get_task_status(context_from)
        if prev and prev.status in ("completed", "failed"):
            return self._build_resume_context(context_from, prev), None
        visible_context_from = self._sanitize_visible(context_from)
        return (
            None,
            SpawnIssue(
                code="context_from_unavailable",
                message=(
                    f"context_from={visible_context_from} not found or not finished; "
                    "resume context not injected."
                ),
            ),
        )

    @staticmethod
    def _child_session_family_key(parent_session_key: str) -> str:
        return f"subagent:{parent_session_key}"

    @classmethod
    def _build_child_session_key(cls, parent_session_key: str, lineage_id: str) -> str:
        return f"{cls._child_session_family_key(parent_session_key)}::{lineage_id}"

    def _resolve_child_session_key(
        self,
        *,
        parent_session_key: str | None,
        child_session_key: str | None,
        lineage_id: str,
    ) -> str | None:
        if isinstance(child_session_key, str) and child_session_key.strip():
            return child_session_key.strip()
        if not isinstance(parent_session_key, str) or not parent_session_key:
            return None
        return self._build_child_session_key(parent_session_key, lineage_id)


    @staticmethod
    def _unknown_child_session_key_issue(candidate: str) -> SpawnIssue:
        return SpawnIssue(
            code="unknown_child_session_key",
            message=(
                f"unknown child_session_key '{candidate}'. {_NEW_TASK_HINT} "
                f"{_CONTINUE_CHILD_HINT} {_PROGRESS_HINT}"
            ),
        )

    @staticmethod
    def _child_session_parent_mismatch_issue() -> SpawnIssue:
        return SpawnIssue(
            code="child_session_parent_mismatch",
            message=(
                "child_session_key does not belong to this parent session. Reuse an exact key "
                f"from this parent's child-session notes, or {_NEW_TASK_HINT.lower()}"
            ),
        )

    def _validate_explicit_child_session_key(
        self,
        *,
        parent_session_key: str | None,
        child_session_key: str | None,
    ) -> SpawnIssue | None:
        if not isinstance(child_session_key, str) or not child_session_key.strip():
            return None
        if self.sessions is None:
            return None
        if not isinstance(parent_session_key, str) or not parent_session_key:
            return SpawnIssue(
                code="child_session_parent_required",
                message=(
                    f"child_session_key requires a parent session. {_NEW_TASK_HINT}"
                ),
            )
        candidate = child_session_key.strip()
        if not self.sessions.session_exists(candidate):
            return self._unknown_child_session_key_issue(candidate)
        session = self.sessions.get_or_create(candidate)
        if session.metadata.get("parent_session_key") != parent_session_key:
            return self._child_session_parent_mismatch_issue()
        return None
