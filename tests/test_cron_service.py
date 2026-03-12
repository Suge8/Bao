import asyncio
import json

from bao.cron.service import CronService
from bao.cron.types import CronSchedule


def test_add_job_rejects_unknown_timezone(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")

    try:
        service.add_job(
            name="tz typo",
            schedule=CronSchedule(kind="cron", expr="0 9 * * *", tz="America/Vancovuer"),
            message="hello",
        )
    except ValueError as e:
        assert str(e) == "unknown timezone 'America/Vancovuer'"
    else:
        raise AssertionError("Expected ValueError for invalid timezone")

    assert service.list_jobs(include_disabled=True) == []


def test_add_job_accepts_valid_timezone(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")

    job = service.add_job(
        name="tz ok",
        schedule=CronSchedule(kind="cron", expr="0 9 * * *", tz="America/Vancouver"),
        message="hello",
    )

    assert job.schedule.tz == "America/Vancouver"
    assert job.state.next_run_at_ms is not None


def test_timer_path_reloads_external_jobs_json(tmp_path) -> None:
    store_path = tmp_path / "cron" / "jobs.json"
    service = CronService(store_path)

    service.add_job(
        name="keep",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        message="hello",
    )
    assert len(service.list_jobs(include_disabled=True)) == 1

    data = json.loads(store_path.read_text(encoding="utf-8"))
    data["jobs"] = []
    store_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    asyncio.run(service._on_timer())

    assert service.list_jobs(include_disabled=True) == []


def test_update_job_rewrites_definition_and_recomputes_next_run(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")

    job = service.add_job(
        name="daily",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        message="hello",
    )

    updated = service.update_job(
        job.id,
        name="weekday digest",
        enabled=False,
        schedule=CronSchedule(kind="cron", expr="0 9 * * 1-5", tz="Australia/Sydney"),
        message="digest",
        deliver=True,
        channel="telegram",
        to="123",
        delete_after_run=True,
    )

    assert updated is not None
    assert updated.name == "weekday digest"
    assert updated.enabled is False
    assert updated.schedule.kind == "cron"
    assert updated.payload.message == "digest"
    assert updated.payload.deliver is True
    assert updated.payload.channel == "telegram"
    assert updated.payload.to == "123"
    assert updated.delete_after_run is True
    assert updated.state.next_run_at_ms is None


def test_change_listener_fires_on_mutations(tmp_path) -> None:
    service = CronService(tmp_path / "cron" / "jobs.json")
    events: list[str] = []

    service.add_change_listener(lambda: events.append("changed"))

    job = service.add_job(
        name="listener",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        message="hello",
    )
    _ = service.enable_job(job.id, False)
    _ = service.remove_job(job.id)

    assert len(events) >= 3
