from __future__ import annotations

import time
from datetime import datetime

from bao.cron.types import CronSchedule


def now_ms() -> int:
    return int(time.time() * 1000)


def compute_next_run(schedule: CronSchedule, reference_ms: int) -> int | None:
    if schedule.kind == "at":
        if schedule.at_ms and schedule.at_ms > reference_ms:
            return schedule.at_ms
        return None
    if schedule.kind == "every":
        if not schedule.every_ms or schedule.every_ms <= 0:
            return None
        return reference_ms + schedule.every_ms
    if schedule.kind != "cron" or not schedule.expr:
        return None
    return _compute_cron_next_run(schedule, reference_ms)


def validate_schedule_for_add(schedule: CronSchedule) -> None:
    if schedule.tz and schedule.kind != "cron":
        raise ValueError("tz can only be used with cron schedules")
    if schedule.kind == "cron" and schedule.tz:
        _validate_timezone(schedule.tz)


def _compute_cron_next_run(schedule: CronSchedule, reference_ms: int) -> int | None:
    try:
        from zoneinfo import ZoneInfo

        from croniter import croniter
    except Exception:
        return None
    try:
        tz = ZoneInfo(schedule.tz) if schedule.tz else datetime.now().astimezone().tzinfo
        base = datetime.fromtimestamp(reference_ms / 1000, tz=tz)
        cron = croniter(schedule.expr, base)
        return int(cron.get_next(datetime).timestamp() * 1000)
    except Exception:
        return None


def _validate_timezone(tz: str) -> None:
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(tz)
    except Exception:
        raise ValueError(f"unknown timezone '{tz}'") from None
