from __future__ import annotations

import asyncio
from pathlib import Path

from bao.agent.tools.coding_session_store import (
    CodingSessionBinding,
    CodingSessionEvent,
    SessionMetadataCodingSessionStore,
    _read_bindings,
)
from bao.session.manager import SessionManager


def _run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


def test_session_metadata_coding_store_round_trip(tmp_path: Path) -> None:
    sessions = SessionManager(tmp_path)
    store = SessionMetadataCodingSessionStore(sessions)

    _run(
        store.publish(
            CodingSessionEvent(
                backend="codex",
                context_key="telegram:alice",
                session_id="sess-1",
                action="active",
            )
        )
    )

    assert _run(store.load(context_key="telegram:alice", backend="codex")) == "sess-1"
    session = sessions.get_or_create("telegram:alice")
    assert session.metadata["coding_sessions"]["codex"]["session_id"] == "sess-1"
    assert _read_bindings(session.metadata) == {"codex": CodingSessionBinding(session_id="sess-1")}


def test_session_metadata_coding_store_clear(tmp_path: Path) -> None:
    sessions = SessionManager(tmp_path)
    store = SessionMetadataCodingSessionStore(sessions)

    _run(
        store.publish(
            CodingSessionEvent(
                backend="codex",
                context_key="telegram:alice",
                session_id="sess-1",
                action="active",
            )
        )
    )
    _run(
        store.publish(
            CodingSessionEvent(
                backend="codex",
                context_key="telegram:alice",
                session_id="sess-1",
                action="cleared",
                reason="stale_session",
            )
        )
    )

    assert _run(store.load(context_key="telegram:alice", backend="codex")) is None
    session = sessions.get_or_create("telegram:alice")
    assert session.metadata.get("coding_sessions") == {}
