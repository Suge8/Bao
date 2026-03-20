from __future__ import annotations

from pathlib import Path

from bao.hub._profile_binding_store import JsonProfileBindingStore


class SessionRouteIndex:
    """Persistent session-to-profile route index for hub dispatch."""

    def __init__(self, path: Path) -> None:
        self._store = JsonProfileBindingStore(path, normalize_key=_normalize_session_key)

    def resolve(self, session_key: object) -> str:
        return self._store.resolve(session_key)

    def bind(self, session_key: object, profile_id: object) -> None:
        self._store.bind(session_key, profile_id)

    def unbind(self, session_key: object) -> None:
        self._store.unbind(session_key)

    def snapshot(self) -> dict[str, str]:
        return self._store.snapshot()


def _normalize_session_key(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()
