from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bao.cron.types import CronSchedule


@dataclass(frozen=True)
class CronAddJobRequest:
    name: str
    schedule: CronSchedule
    message: str
    enabled: bool = True
    deliver: bool = False
    channel: str | None = None
    to: str | None = None
    delete_after_run: bool = False


@dataclass(frozen=True)
class CronUpdateJobRequest:
    job_id: str
    name: str
    enabled: bool
    schedule: CronSchedule
    message: str
    deliver: bool = False
    channel: str | None = None
    to: str | None = None
    delete_after_run: bool = False


@dataclass(frozen=True)
class _LegacyArgLookup:
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    index: int
    key: str
    default: Any


def coerce_add_request(
    primary: CronAddJobRequest | str | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> CronAddJobRequest:
    if isinstance(primary, CronAddJobRequest):
        if args or kwargs:
            raise TypeError("CronAddJobRequest call does not accept extra args")
        return primary
    if isinstance(primary, str):
        return _coerce_add_from_primary_name(primary, args, kwargs)
    if primary is None:
        return _coerce_add_from_kwargs(kwargs)
    raise TypeError("add_job expects CronAddJobRequest or legacy name/schedule/message input")


def coerce_update_request(
    primary: CronUpdateJobRequest | str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> CronUpdateJobRequest:
    if isinstance(primary, CronUpdateJobRequest):
        if args or kwargs:
            raise TypeError("CronUpdateJobRequest call does not accept extra args")
        return primary
    if isinstance(primary, str):
        if args:
            raise TypeError("legacy update_job only supports keyword updates")
        return _coerce_update_from_kwargs(primary, kwargs)
    raise TypeError("update_job expects CronUpdateJobRequest or legacy job_id + keyword fields")


def _coerce_add_from_primary_name(
    name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> CronAddJobRequest:
    if len(args) < 2:
        raise TypeError("legacy add_job(name, schedule, message, ...) requires schedule and message")
    schedule = args[0]
    message = args[1]
    if not isinstance(schedule, CronSchedule):
        raise TypeError("schedule must be CronSchedule")
    enabled = bool(_legacy_arg(_LegacyArgLookup(args, kwargs, 2, "enabled", True)))
    deliver = bool(_legacy_arg(_LegacyArgLookup(args, kwargs, 3, "deliver", False)))
    channel = _coerce_optional_str(_legacy_arg(_LegacyArgLookup(args, kwargs, 4, "channel", None)))
    target = _coerce_optional_str(_legacy_arg(_LegacyArgLookup(args, kwargs, 5, "to", None)))
    delete_after = bool(_legacy_arg(_LegacyArgLookup(args, kwargs, 6, "delete_after_run", False)))
    return CronAddJobRequest(
        name=name,
        schedule=schedule,
        message=str(message),
        enabled=enabled,
        deliver=deliver,
        channel=channel,
        to=target,
        delete_after_run=delete_after,
    )


def _coerce_add_from_kwargs(kwargs: dict[str, Any]) -> CronAddJobRequest:
    name = kwargs.get("name")
    schedule = kwargs.get("schedule")
    message = kwargs.get("message")
    if not isinstance(name, str) or not isinstance(schedule, CronSchedule):
        raise TypeError("add_job keyword mode requires name:str and schedule:CronSchedule")
    return CronAddJobRequest(
        name=name,
        schedule=schedule,
        message=str(message or ""),
        enabled=bool(kwargs.get("enabled", True)),
        deliver=bool(kwargs.get("deliver", False)),
        channel=_coerce_optional_str(kwargs.get("channel")),
        to=_coerce_optional_str(kwargs.get("to")),
        delete_after_run=bool(kwargs.get("delete_after_run", False)),
    )


def _coerce_update_from_kwargs(job_id: str, kwargs: dict[str, Any]) -> CronUpdateJobRequest:
    schedule = kwargs.get("schedule")
    if not isinstance(schedule, CronSchedule):
        raise TypeError("update_job requires schedule:CronSchedule")
    return CronUpdateJobRequest(
        job_id=job_id,
        name=str(kwargs.get("name", "")),
        enabled=bool(kwargs.get("enabled", True)),
        schedule=schedule,
        message=str(kwargs.get("message", "")),
        deliver=bool(kwargs.get("deliver", False)),
        channel=_coerce_optional_str(kwargs.get("channel")),
        to=_coerce_optional_str(kwargs.get("to")),
        delete_after_run=bool(kwargs.get("delete_after_run", False)),
    )


def _legacy_arg(lookup: _LegacyArgLookup) -> Any:
    if lookup.index < len(lookup.args):
        return lookup.args[lookup.index]
    if lookup.key in lookup.kwargs:
        return lookup.kwargs[lookup.key]
    return lookup.default


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
