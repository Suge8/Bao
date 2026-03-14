from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from bao.session.manager import SessionManager


@dataclass(frozen=True)
class CodingSessionEvent:
    backend: str
    context_key: str
    session_id: str | None
    action: Literal["active", "cleared"]
    reason: str | None = None


@dataclass(frozen=True)
class CodingSessionBinding:
    session_id: str


class CodingSessionStore(Protocol):
    async def load(self, *, context_key: str, backend: str) -> str | None: ...

    async def publish(self, event: CodingSessionEvent) -> None: ...


def _clean_session_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


_CODING_SESSIONS_KEY = "coding_sessions"


def _read_bindings(metadata: dict[str, Any]) -> dict[str, CodingSessionBinding]:
    raw = metadata.get(_CODING_SESSIONS_KEY)
    if not isinstance(raw, dict):
        return {}
    bindings: dict[str, CodingSessionBinding] = {}
    for backend, state in raw.items():
        if not isinstance(backend, str) or not backend.strip() or not isinstance(state, dict):
            continue
        session_id = _clean_session_id(state.get("session_id"))
        if session_id is None:
            continue
        bindings[backend] = CodingSessionBinding(session_id=session_id)
    return bindings


def _serialize_bindings(bindings: dict[str, CodingSessionBinding]) -> dict[str, dict[str, str]]:
    payload: dict[str, dict[str, str]] = {}
    for backend, binding in bindings.items():
        normalized_backend = backend.strip()
        if not normalized_backend or not isinstance(binding, CodingSessionBinding):
            continue
        payload[normalized_backend] = {"session_id": binding.session_id}
    return payload


def _binding_for(
    metadata: dict[str, Any],
    *,
    backend: str,
) -> CodingSessionBinding | None:
    return _read_bindings(metadata).get(backend)


def _next_bindings_for_event(
    bindings: dict[str, CodingSessionBinding],
    event: CodingSessionEvent,
) -> dict[str, CodingSessionBinding] | None:
    next_bindings = dict(bindings)
    backend = event.backend.strip()
    if event.action == "active":
        session_id = _clean_session_id(event.session_id)
        if session_id is None:
            return None
        current = next_bindings.get(backend)
        if current and current.session_id == session_id:
            return None
        next_bindings[backend] = CodingSessionBinding(session_id=session_id)
        return next_bindings
    if event.action == "cleared":
        if backend not in next_bindings:
            return None
        next_bindings.pop(backend, None)
        return next_bindings
    return None


class SessionMetadataCodingSessionStore:
    def __init__(self, sessions: "SessionManager"):
        self._sessions = sessions

    async def load(self, *, context_key: str, backend: str) -> str | None:
        return await asyncio.to_thread(self._load_sync, context_key, backend)

    async def publish(self, event: CodingSessionEvent) -> None:
        await asyncio.to_thread(self._publish_sync, event)

    def _load_sync(self, context_key: str, backend: str) -> str | None:
        if not context_key or not backend:
            return None
        session = self._sessions.get_or_create(context_key)
        binding = _binding_for(session.metadata, backend=backend)
        return binding.session_id if binding else None

    def _publish_sync(self, event: CodingSessionEvent) -> None:
        context_key = event.context_key.strip()
        backend = event.backend.strip()
        if not context_key or not backend:
            return
        self._sessions.ensure_session_meta(context_key)
        session = self._sessions.get_or_create(context_key)
        next_bindings = _next_bindings_for_event(_read_bindings(session.metadata), event)
        if next_bindings is None:
            return

        self._sessions.update_metadata_only(
            context_key,
            {_CODING_SESSIONS_KEY: _serialize_bindings(next_bindings)},
            emit_change=True,
        )
