from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable

KeyNormalizer = Callable[[object], str]


class JsonProfileBindingStore:
    def __init__(self, path: Path, *, normalize_key: KeyNormalizer) -> None:
        self._path = Path(path).expanduser()
        self._normalize_key = normalize_key
        self._lock = threading.RLock()
        self._bindings: dict[str, str] = {}
        self._loaded = False

    def resolve(self, key: object) -> str:
        normalized_key = self._normalize_key(key)
        if not normalized_key:
            return ""
        with self._lock:
            self._ensure_loaded()
            return self._bindings.get(normalized_key, "")

    def bind(self, key: object, profile_id: object) -> None:
        normalized_key = self._normalize_key(key)
        normalized_profile = _normalize_profile_id(profile_id)
        if not normalized_key or not normalized_profile:
            return
        with self._lock:
            self._ensure_loaded()
            if self._bindings.get(normalized_key) == normalized_profile:
                return
            self._bindings[normalized_key] = normalized_profile
            self._flush_unlocked()

    def unbind(self, key: object) -> None:
        normalized_key = self._normalize_key(key)
        if not normalized_key:
            return
        with self._lock:
            self._ensure_loaded()
            if normalized_key not in self._bindings:
                return
            self._bindings.pop(normalized_key, None)
            self._flush_unlocked()

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            self._ensure_loaded()
            return dict(self._bindings)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path.exists():
            self._bindings = {}
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            self._bindings = {}
            return
        if not isinstance(raw, dict):
            self._bindings = {}
            return
        self._bindings = {
            key: value
            for key, value in (
                (self._normalize_key(binding_key), _normalize_profile_id(profile_id))
                for binding_key, profile_id in raw.items()
            )
            if key and value
        }

    def _flush_unlocked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._bindings, indent=2, ensure_ascii=False) + "\n"
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self._path.parent,
            prefix=f".{self._path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        temp_path.replace(self._path)


def _normalize_profile_id(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()
