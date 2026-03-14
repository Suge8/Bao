from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def load_probe_results(base_dir: str | Path) -> dict[str, dict[str, object]]:
    path = _cache_path(base_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    results: dict[str, dict[str, object]] = {}
    for name, value in data.items():
        if not isinstance(name, str) or not isinstance(value, dict):
            continue
        results[name] = dict(value)
    return results


def save_probe_result(base_dir: str | Path, name: str, payload: dict[str, Any]) -> dict[str, object]:
    cache = load_probe_results(base_dir)
    entry = dict(payload)
    entry["probedAt"] = datetime.now().isoformat(timespec="seconds")
    cache[name] = entry
    _write_cache(base_dir, cache)
    return entry


def delete_probe_result(base_dir: str | Path, name: str) -> None:
    cache = load_probe_results(base_dir)
    if name not in cache:
        return
    cache.pop(name, None)
    _write_cache(base_dir, cache)


def _cache_path(base_dir: str | Path) -> Path:
    return Path(base_dir).expanduser() / "cache" / "tool-probes.json"


def _write_cache(base_dir: str | Path, payload: dict[str, dict[str, object]]) -> None:
    path = _cache_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
