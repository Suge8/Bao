from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ._profile_common import (
    PROFILE_REGISTRY_VERSION,
    _REGISTRY_MUTEX,
    _data_root,
    _default_registry,
    _make_registry,
    _registry_path,
    ProfileRegistry,
)


def _registry_payload(registry: ProfileRegistry) -> dict[str, Any]:
    return {
        "version": PROFILE_REGISTRY_VERSION,
        "default_profile_id": registry.default_profile_id,
        "active_profile_id": registry.active_profile_id,
        "profiles": [asdict(profile) for profile in registry.profiles],
    }


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _lock_registry_file(handle: Any) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        handle.write("\0")
        handle.flush()
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock_registry_file(handle: Any) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _registry_operation(data_dir: Path | None = None):
    lock_path = _data_root(data_dir) / "profiles.lock"
    with _REGISTRY_MUTEX:
        with lock_path.open("a+", encoding="utf-8") as handle:
            _lock_registry_file(handle)
            try:
                yield
            finally:
                _unlock_registry_file(handle)


def save_profile_registry(registry: ProfileRegistry, *, data_dir: Path | None = None) -> Path:
    path = _registry_path(data_dir)
    _atomic_write_text(
        path,
        json.dumps(_registry_payload(registry), indent=2, ensure_ascii=False) + "\n",
    )
    return path


def _load_profile_registry(path: Path) -> tuple[ProfileRegistry, bool]:
    if not path.exists():
        return _default_registry(), True
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_registry(), True
    if not isinstance(raw, dict):
        return _default_registry(), True
    registry = _make_registry(raw)
    raw_profiles = raw.get("profiles")
    needs_save = any(
        isinstance(item, dict) and "storage_key" not in item and "storageKey" not in item
        for item in (raw_profiles if isinstance(raw_profiles, list) else [])
    )
    return registry, needs_save
