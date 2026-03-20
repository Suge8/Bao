"""Cron service for scheduling agent tasks."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Coroutine

from loguru import logger

from bao.cron._service_requests import (
    CronAddJobRequest,
    CronUpdateJobRequest,
    coerce_add_request,
    coerce_update_request,
)
from bao.cron._service_runtime import (
    arm_timer,
    execute_job,
    get_next_wake_ms,
    on_timer,
    recompute_next_runs,
)
from bao.cron._service_schedule import compute_next_run, now_ms, validate_schedule_for_add
from bao.cron._service_store import LoadStoreRequest, SaveStoreRequest, load_store, save_store
from bao.cron.types import CronJob, CronJobState, CronPayload, CronStore


class CronService:
    """Service for managing and executing scheduled jobs."""

    def __init__(
        self,
        store_path: Path,
        on_job: Callable[[CronJob], Coroutine[Any, Any, str | None]] | None = None,
    ):
        self.store_path = store_path
        self.on_job = on_job
        self._store: CronStore | None = None
        self._last_mtime: float = 0.0
        self._timer_task: asyncio.Task[None] | None = None
        self._running = False
        self._change_listeners: list[Callable[[], None]] = []

    def add_change_listener(self, listener: Callable[[], None]) -> None:
        if listener not in self._change_listeners:
            self._change_listeners.append(listener)

    def remove_change_listener(self, listener: Callable[[], None]) -> None:
        if listener in self._change_listeners:
            self._change_listeners.remove(listener)

    def _notify_changed(self) -> None:
        for listener in list(self._change_listeners):
            try:
                listener()
            except Exception as exc:
                logger.debug("Skip cron change listener: {}", exc)

    def _load_store(self) -> CronStore:
        result = load_store(
            LoadStoreRequest(
                store_path=self.store_path,
                cached_store=self._store,
                last_mtime=self._last_mtime,
            )
        )
        if result.externally_modified:
            logger.info("Cron: jobs.json modified externally, reloading")
        if result.load_error:
            logger.warning("⚠️ 定时存储读取失败 / load failed: {}", result.load_error)
        self._store = result.store
        self._last_mtime = result.mtime
        return self._store

    def _save_store(self) -> None:
        if not self._store:
            return
        self._last_mtime = save_store(SaveStoreRequest(store_path=self.store_path, store=self._store))
        self._notify_changed()

    async def start(self) -> None:
        """Start the cron service."""
        self._running = True
        store = self._load_store()
        recompute_next_runs(store)
        self._save_store()
        arm_timer(self)
        logger.info(
            "⏰ 定时服务已启动 / started: {} jobs", len(self._store.jobs if self._store else [])
        )

    def stop(self) -> None:
        """Stop the cron service."""
        self._running = False
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None

    def _arm_timer(self) -> None:
        arm_timer(self)

    async def _on_timer(self) -> None:
        await on_timer(self)

    async def _execute_job(self, job: CronJob) -> None:
        await execute_job(self, job)

    # ========== Public API ==========

    def list_jobs(self, include_disabled: bool = False) -> list[CronJob]:
        """List all jobs."""
        store = self._load_store()
        jobs = store.jobs if include_disabled else [j for j in store.jobs if j.enabled]
        return sorted(jobs, key=lambda j: j.state.next_run_at_ms or float("inf"))

    def get_job(self, job_id: str) -> CronJob | None:
        store = self._load_store()
        for job in store.jobs:
            if job.id == job_id:
                return job
        return None

    def add_job(
        self,
        request: CronAddJobRequest | str | None = None,
        *legacy_args: Any,
        **legacy_kwargs: Any,
    ) -> CronJob:
        """Add a new job."""
        store = self._load_store()
        normalized = coerce_add_request(request, legacy_args, legacy_kwargs)
        validate_schedule_for_add(normalized.schedule)
        current_ms = now_ms()

        job = CronJob(
            id=str(uuid.uuid4())[:8],
            name=normalized.name,
            enabled=normalized.enabled,
            schedule=normalized.schedule,
            payload=CronPayload(
                kind="agent_turn",
                message=normalized.message,
                deliver=normalized.deliver,
                channel=normalized.channel,
                to=normalized.to,
            ),
            state=CronJobState(
                next_run_at_ms=compute_next_run(normalized.schedule, current_ms)
                if normalized.enabled
                else None
            ),
            created_at_ms=current_ms,
            updated_at_ms=current_ms,
            delete_after_run=normalized.delete_after_run,
        )

        store.jobs.append(job)
        self._save_store()
        arm_timer(self)

        logger.debug("⏰ 定时任务已添加 / added: '{}' ({})", normalized.name, job.id)
        return job

    def update_job(
        self,
        request: CronUpdateJobRequest | str,
        *legacy_args: Any,
        **legacy_kwargs: Any,
    ) -> CronJob | None:
        store = self._load_store()
        normalized = coerce_update_request(request, legacy_args, legacy_kwargs)
        validate_schedule_for_add(normalized.schedule)
        current_ms = now_ms()
        for job in store.jobs:
            if job.id != normalized.job_id:
                continue
            job.name = normalized.name
            job.enabled = normalized.enabled
            job.schedule = normalized.schedule
            job.payload.kind = "agent_turn"
            job.payload.message = normalized.message
            job.payload.deliver = normalized.deliver
            job.payload.channel = normalized.channel
            job.payload.to = normalized.to
            job.delete_after_run = normalized.delete_after_run
            job.updated_at_ms = current_ms
            job.state.next_run_at_ms = (
                compute_next_run(normalized.schedule, current_ms) if normalized.enabled else None
            )
            self._save_store()
            arm_timer(self)
            logger.debug("⏰ 定时任务已更新 / updated: '{}' ({})", normalized.name, job.id)
            return job
        return None

    def remove_job(self, job_id: str) -> bool:
        """Remove a job by ID."""
        store = self._load_store()
        before = len(store.jobs)
        store.jobs = [j for j in store.jobs if j.id != job_id]
        removed = len(store.jobs) < before

        if removed:
            self._save_store()
            arm_timer(self)
            logger.debug("⏰ 定时任务已移除 / removed: {}", job_id)

        return removed

    def enable_job(self, job_id: str, enabled: bool = True) -> CronJob | None:
        """Enable or disable a job."""
        store = self._load_store()
        for job in store.jobs:
            if job.id == job_id:
                job.enabled = enabled
                job.updated_at_ms = now_ms()
                if enabled:
                    job.state.next_run_at_ms = compute_next_run(job.schedule, now_ms())
                else:
                    job.state.next_run_at_ms = None
                self._save_store()
                arm_timer(self)
                return job
        return None

    async def run_job(self, job_id: str, force: bool = False) -> bool:
        """Manually run a job."""
        store = self._load_store()
        for job in store.jobs:
            if job.id == job_id:
                if not force and not job.enabled:
                    return False
                await self._execute_job(job)
                self._save_store()
                arm_timer(self)
                return True
        return False

    def status(self) -> dict[str, Any]:
        """Get service status."""
        store = self._load_store()
        return {
            "enabled": self._running,
            "jobs": len(store.jobs),
            "next_wake_at_ms": get_next_wake_ms(store),
        }
