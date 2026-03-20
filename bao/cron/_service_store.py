from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from bao.cron.types import CronJob, CronJobState, CronPayload, CronSchedule, CronStore


@dataclass(frozen=True)
class LoadStoreRequest:
    store_path: Path
    cached_store: CronStore | None
    last_mtime: float


@dataclass(frozen=True)
class LoadStoreResult:
    store: CronStore
    mtime: float
    externally_modified: bool
    load_error: Exception | None = None


@dataclass(frozen=True)
class SaveStoreRequest:
    store_path: Path
    store: CronStore


def load_store(request: LoadStoreRequest) -> LoadStoreResult:
    if _can_reuse_cached_store(request):
        return LoadStoreResult(
            store=request.cached_store or CronStore(),
            mtime=request.last_mtime,
            externally_modified=False,
        )
    if not request.store_path.exists():
        return LoadStoreResult(store=CronStore(), mtime=0.0, externally_modified=False)
    try:
        data = json.loads(request.store_path.read_text(encoding="utf-8"))
        store = _parse_store(data)
        return LoadStoreResult(
            store=store,
            mtime=request.store_path.stat().st_mtime,
            externally_modified=request.cached_store is not None,
        )
    except Exception as exc:
        return LoadStoreResult(
            store=CronStore(),
            mtime=0.0,
            externally_modified=False,
            load_error=exc,
        )


def save_store(request: SaveStoreRequest) -> float:
    request.store_path.parent.mkdir(parents=True, exist_ok=True)
    data = _serialize_store(request.store)
    request.store_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return request.store_path.stat().st_mtime


def _can_reuse_cached_store(request: LoadStoreRequest) -> bool:
    if request.cached_store is None or not request.store_path.exists():
        return False
    current_mtime = request.store_path.stat().st_mtime
    return current_mtime == request.last_mtime


def _parse_store(data: dict[str, object]) -> CronStore:
    jobs = [_parse_job(raw) for raw in data.get("jobs", []) if isinstance(raw, dict)]
    return CronStore(jobs=jobs)


def _parse_job(payload: dict[str, object]) -> CronJob:
    schedule_data = payload.get("schedule", {})
    payload_data = payload.get("payload", {})
    state_data = payload.get("state", {})
    return CronJob(
        id=str(payload.get("id", "")),
        name=str(payload.get("name", "")),
        enabled=bool(payload.get("enabled", True)),
        schedule=CronSchedule(
            kind=str(schedule_data.get("kind", "every")),
            at_ms=schedule_data.get("atMs"),
            every_ms=schedule_data.get("everyMs"),
            expr=schedule_data.get("expr"),
            tz=schedule_data.get("tz"),
        ),
        payload=CronPayload(
            kind=str(payload_data.get("kind", "agent_turn")),
            message=str(payload_data.get("message", "")),
            deliver=bool(payload_data.get("deliver", False)),
            channel=payload_data.get("channel"),
            to=payload_data.get("to"),
        ),
        state=CronJobState(
            next_run_at_ms=state_data.get("nextRunAtMs"),
            last_run_at_ms=state_data.get("lastRunAtMs"),
            last_status=state_data.get("lastStatus"),
            last_error=state_data.get("lastError"),
        ),
        created_at_ms=int(payload.get("createdAtMs", 0)),
        updated_at_ms=int(payload.get("updatedAtMs", 0)),
        delete_after_run=bool(payload.get("deleteAfterRun", False)),
    )


def _serialize_store(store: CronStore) -> dict[str, object]:
    return {
        "version": store.version,
        "jobs": [_serialize_job(job) for job in store.jobs],
    }


def _serialize_job(job: CronJob) -> dict[str, object]:
    return {
        "id": job.id,
        "name": job.name,
        "enabled": job.enabled,
        "schedule": {
            "kind": job.schedule.kind,
            "atMs": job.schedule.at_ms,
            "everyMs": job.schedule.every_ms,
            "expr": job.schedule.expr,
            "tz": job.schedule.tz,
        },
        "payload": {
            "kind": job.payload.kind,
            "message": job.payload.message,
            "deliver": job.payload.deliver,
            "channel": job.payload.channel,
            "to": job.payload.to,
        },
        "state": {
            "nextRunAtMs": job.state.next_run_at_ms,
            "lastRunAtMs": job.state.last_run_at_ms,
            "lastStatus": job.state.last_status,
            "lastError": job.state.last_error,
        },
        "createdAtMs": job.created_at_ms,
        "updatedAtMs": job.updated_at_ms,
        "deleteAfterRun": job.delete_after_run,
    }
