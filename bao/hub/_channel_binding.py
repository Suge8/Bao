from __future__ import annotations

from pathlib import Path

from bao.hub._profile_binding_store import JsonProfileBindingStore


class ChannelBindingStore:
    """Persistent origin-to-profile binding store for deterministic route misses."""

    def __init__(self, path: Path) -> None:
        self._store = JsonProfileBindingStore(path, normalize_key=_normalize_origin_key)

    def resolve(self, origin_key: object) -> str:
        return self._store.resolve(origin_key)

    def bind(self, origin_key: object, profile_id: object) -> None:
        self._store.bind(origin_key, profile_id)

    def snapshot(self) -> dict[str, str]:
        return self._store.snapshot()


def _normalize_origin_key(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()
