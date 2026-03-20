from __future__ import annotations

import time
from dataclasses import dataclass, field

_CACHE_TTL_SECONDS = 120.0


@dataclass(frozen=True)
class CodingBackendHealth:
    backend: str
    ready: bool
    error_type: str = ""
    message: str = ""
    hints: tuple[str, ...] = field(default_factory=tuple)
    checked_at: float = field(default_factory=time.time)


@dataclass
class _CacheEntry:
    value: CodingBackendHealth
    expires_at: float


_CACHE: dict[tuple[str, str], _CacheEntry] = {}


def get_cached_backend_health(backend: str, workspace: str) -> CodingBackendHealth | None:
    entry = _CACHE.get((backend, workspace))
    if entry is None:
        return None
    if entry.expires_at < time.time():
        _CACHE.pop((backend, workspace), None)
        return None
    return entry.value


def set_cached_backend_health(
    backend: str,
    workspace: str,
    value: CodingBackendHealth,
) -> CodingBackendHealth:
    _CACHE[(backend, workspace)] = _CacheEntry(
        value=value,
        expires_at=time.time() + _CACHE_TTL_SECONDS,
    )
    return value


def format_backend_issue(value: CodingBackendHealth) -> str:
    if value.ready:
        return ""
    detail = value.message.strip() or value.error_type.strip() or "backend unavailable"
    prefix = f"{value.backend}:"
    if detail.startswith(prefix):
        detail = detail[len(prefix) :].strip()
    suffix = ""
    if value.hints:
        suffix = f" Next: {value.hints[0]}"
    return f"{value.backend}: {detail}{suffix}"
