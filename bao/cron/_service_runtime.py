from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from bao.cron._service_schedule import compute_next_run, now_ms
from bao.cron.types import CronJob, CronStore


def recompute_next_runs(store: CronStore) -> None:
    current_ms = now_ms()
    for job in store.jobs:
        if job.enabled:
            job.state.next_run_at_ms = compute_next_run(job.schedule, current_ms)


def get_next_wake_ms(store: CronStore | None) -> int | None:
    if store is None:
        return None
    candidates = [
        job.state.next_run_at_ms
        for job in store.jobs
        if job.enabled and job.state.next_run_at_ms is not None
    ]
    return min(candidates) if candidates else None


def arm_timer(service: Any) -> None:
    if service._timer_task:
        service._timer_task.cancel()
    next_wake = get_next_wake_ms(service._store)
    if next_wake is None or not service._running:
        return
    delay_s = max(0, next_wake - now_ms()) / 1000
    service._timer_task = asyncio.create_task(_run_timer_tick(service, delay_s))


async def on_timer(service: Any) -> None:
    store = service._load_store()
    due_jobs = _collect_due_jobs(store)
    for job in due_jobs:
        await execute_job(service, job)
    service._save_store()
    arm_timer(service)


async def execute_job(service: Any, job: CronJob) -> None:
    started_at = now_ms()
    logger.debug("⏰ 定时任务执行 / executing: '{}' ({})", job.name, job.id)
    await _run_job_callback(service, job)
    job.state.last_run_at_ms = started_at
    job.updated_at_ms = now_ms()
    _apply_post_run_state(service, job)


def _collect_due_jobs(store: CronStore) -> list[CronJob]:
    current_ms = now_ms()
    return [
        job
        for job in store.jobs
        if job.enabled and job.state.next_run_at_ms is not None and current_ms >= job.state.next_run_at_ms
    ]


async def _run_timer_tick(service: Any, delay_s: float) -> None:
    await asyncio.sleep(delay_s)
    if service._running:
        await on_timer(service)


async def _run_job_callback(service: Any, job: CronJob) -> None:
    try:
        if service.on_job:
            await service.on_job(job)
        job.state.last_status = "ok"
        job.state.last_error = None
        logger.debug("⏰ 定时任务完成 / completed: '{}'", job.name)
    except Exception as exc:
        job.state.last_status = "error"
        job.state.last_error = str(exc)
        logger.error("❌ 定时任务失败 / cron failed: '{}' — {}", job.name, exc)


def _apply_post_run_state(service: Any, job: CronJob) -> None:
    if job.schedule.kind == "at":
        _apply_one_shot_state(service, job)
        return
    job.state.next_run_at_ms = compute_next_run(job.schedule, now_ms())


def _apply_one_shot_state(service: Any, job: CronJob) -> None:
    if not job.delete_after_run:
        job.enabled = False
        job.state.next_run_at_ms = None
        return
    if service._store is None:
        return
    service._store.jobs = [candidate for candidate in service._store.jobs if candidate.id != job.id]
