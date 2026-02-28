"""API mode probe cache — probe once, remember forever.

Stores per-endpoint API mode detection results to avoid repeated probing.
Cache is persisted to ``~/.bao/api_mode_cache.json`` with a 7-day TTL.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

_CACHE_FILE = Path.home() / ".bao" / "api_mode_cache.json"
_TTL_SECONDS = 7 * 24 * 3600

_cache: dict[str, Any] | None = None


def _load() -> dict[str, Any]:
    global _cache
    if _cache is None:
        loaded: dict[str, Any] = {}
        if _CACHE_FILE.exists():
            try:
                loaded = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        _cache = loaded
    return _cache


def _save() -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(_load(), indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.debug("🤖 缓存保存失败 / save failed: {}", e)


def _normalize_key(api_base: str) -> str:
    """Normalize api_base URL to a consistent cache key."""
    return api_base.rstrip("/").lower()


def get_cached_mode(api_base: str) -> str | None:
    """Get cached API mode for an endpoint.

    Returns ``"responses"`` or ``"completions"``, or ``None`` if not
    cached or expired.
    """
    key = _normalize_key(api_base)
    cache = _load()
    entry = cache.get(key)
    if not entry:
        return None
    if time.time() - entry.get("probed_at", 0) > _TTL_SECONDS:
        cache.pop(key, None)
        _save()
        return None
    return entry.get("mode")


def set_cached_mode(api_base: str, mode: str) -> None:
    """Cache the detected API mode for an endpoint."""
    key = _normalize_key(api_base)
    _load()[key] = {"mode": mode, "probed_at": time.time()}
    _save()
    logger.debug("🤖 模式已缓存 / cached: {} → {}", key, mode)
