from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from bao.hub._route_resolution import SessionOrigin
from bao.session.manager import SessionChangeEvent

from ._session_directory_bindings import SessionDirectoryBindings
from ._session_directory_models import SessionBindingRecord, SessionRecord
from ._session_directory_store import SessionDirectoryStore

_RUNTIME_ATTR = "_hub_session_directory_runtime"
_TOPIC_MARKER = ":topic:"


@dataclass(frozen=True, slots=True)
class SessionDirectoryRuntime:
    store: SessionDirectoryStore
    updater: "SessionDirectoryUpdater"
    bindings: SessionDirectoryBindings


def get_session_directory_runtime(session_manager: Any) -> SessionDirectoryRuntime:
    runtime = getattr(session_manager, _RUNTIME_ATTR, None)
    if isinstance(runtime, SessionDirectoryRuntime):
        return runtime
    workspace = getattr(session_manager, "workspace", None)
    root = Path(str(workspace)).expanduser()
    store = SessionDirectoryStore(root)
    updater = SessionDirectoryUpdater(session_manager=session_manager, store=store)
    bindings = SessionDirectoryBindings(store)
    add_listener = getattr(session_manager, "add_change_listener", None)
    if callable(add_listener):
        add_listener(updater.handle_session_change)
    runtime = SessionDirectoryRuntime(store=store, updater=updater, bindings=bindings)
    setattr(session_manager, _RUNTIME_ATTR, runtime)
    return runtime


class SessionDirectoryUpdater:
    def __init__(self, *, session_manager: Any, store: SessionDirectoryStore) -> None:
        self._session_manager = session_manager
        self._store = store

    def observe_origin(self, session_key: object, origin: SessionOrigin) -> None:
        normalized_key = str(session_key or "").strip()
        if not normalized_key:
            return
        self._refresh_session(normalized_key, event_kind="messages", origin=origin)

    def mark_archived(self, session_key: object, archived: bool) -> None:
        normalized_key = str(session_key or "").strip()
        current = self._store.get_record(normalized_key)
        if current is None:
            return
        availability = "archived" if archived else "dormant"
        self._store.upsert_record(
            SessionRecord.create(
                **_record_payload(current, availability=availability, archived=archived, updated_at=_now_iso()),
            )
        )

    def mark_unreachable(self, session_key: object) -> None:
        normalized_key = str(session_key or "").strip()
        current = self._store.get_record(normalized_key)
        if current is None:
            return
        self._store.upsert_record(
            SessionRecord.create(
                **_record_payload(current, availability="unreachable", updated_at=_now_iso()),
            )
        )

    def mark_deleted(self, session_key: object) -> None:
        normalized_key = str(session_key or "").strip()
        current = self._store.get_record(normalized_key)
        if current is None:
            return
        updated_at = _now_iso()
        self._store.upsert_record(
            SessionRecord.create(
                **_record_payload(current, availability="deleted", archived=True, updated_at=updated_at),
            )
        )
        self._store.delete_observed_bindings_for_session(current.session_ref)

    def handle_session_change(self, event: object) -> None:
        if not isinstance(event, SessionChangeEvent):
            return
        if event.kind == "deleted":
            self.mark_deleted(event.session_key)
            return
        self._refresh_session(event.session_key, event_kind=event.kind, origin=None)

    def _refresh_session(
        self,
        session_key: str,
        *,
        event_kind: str,
        origin: SessionOrigin | None,
    ) -> None:
        current = self._store.get_record(session_key)
        entry = self._session_entry(session_key)
        if entry is None and current is None and origin is None:
            return
        if not self._should_materialize(entry, current, origin):
            return
        record = self._build_record(
            session_key=session_key,
            current=current,
            entry=entry or {},
            event_kind=event_kind,
            origin=origin,
        )
        self._store.upsert_record(record)
        binding_key = record.binding_key()
        if binding_key and record.availability != "deleted":
            self._store.upsert_binding(
                SessionBindingRecord.create(
                    session_ref=record.session_ref,
                    channel=record.channel,
                    account_id=record.account_id,
                    peer_id=record.peer_id,
                    thread_id=record.thread_id,
                    source="observed",
                    updated_at=record.updated_at,
                )
            )

    def _session_entry(self, session_key: str) -> dict[str, Any] | None:
        get_entry = getattr(self._session_manager, "get_session_list_entry", None)
        if not callable(get_entry):
            return None
        entry = get_entry(session_key)
        return dict(entry) if isinstance(entry, dict) else None

    @staticmethod
    def _should_materialize(
        entry: dict[str, Any] | None,
        current: SessionRecord | None,
        origin: SessionOrigin | None,
    ) -> bool:
        if current is not None or origin is not None:
            return True
        if not isinstance(entry, dict):
            return False
        has_messages = entry.get("has_messages")
        message_count = entry.get("message_count")
        if has_messages is True:
            return True
        return isinstance(message_count, int) and message_count > 0

    def _build_record(
        self,
        *,
        session_key: str,
        current: SessionRecord | None,
        entry: dict[str, Any],
        event_kind: str,
        origin: SessionOrigin | None,
    ) -> SessionRecord:
        parsed = _parse_session_route(session_key)
        routing = entry.get("routing") if isinstance(entry.get("routing"), dict) else {}
        runtime = entry.get("runtime") if isinstance(entry.get("runtime"), dict) else {}
        view = entry.get("view") if isinstance(entry.get("view"), dict) else {}
        current_snapshot = current.as_snapshot() if current is not None else {}
        updated_at = str(entry.get("updated_at") or current_snapshot.get("updated_at") or _now_iso())
        channel = (origin.channel if origin is not None else "") or str(current_snapshot.get("channel") or "") or parsed.channel
        account_id = (origin.account_id if origin is not None else "") or str(current_snapshot.get("account_id") or "")
        peer_id = (origin.peer_id if origin is not None else "") or str(current_snapshot.get("peer_id") or "") or parsed.peer_id
        thread_id = (origin.thread_id if origin is not None else "") or str(current_snapshot.get("thread_id") or "") or parsed.thread_id
        availability = self._next_availability(current, runtime=runtime, event_kind=event_kind)
        last_active_at = str(current_snapshot.get("last_active_at") or "")
        if availability == "active":
            last_active_at = updated_at
        participants_preview = current.participants_preview if current is not None else ()
        return SessionRecord.create(
            session_ref=str(current_snapshot.get("session_ref") or ""),
            session_key=session_key,
            channel=channel,
            account_id=account_id,
            peer_id=peer_id,
            thread_id=thread_id,
            title=view.get("title") or current_snapshot.get("title") or "",
            handle=str(current_snapshot.get("handle") or peer_id or ""),
            kind=routing.get("session_kind") or current_snapshot.get("kind") or "",
            updated_at=updated_at,
            last_active_at=last_active_at,
            availability=availability,
            archived=availability in {"archived", "deleted"},
            participants_preview=participants_preview,
        )

    @staticmethod
    def _next_availability(
        current: SessionRecord | None,
        *,
        runtime: dict[str, Any],
        event_kind: str,
    ) -> str:
        current_value = current.availability if current is not None else "dormant"
        if current_value in {"archived", "deleted", "unreachable"} and event_kind != "messages":
            return current_value
        if event_kind == "messages" or bool(runtime.get("is_running")):
            return "active"
        return "dormant"


@dataclass(frozen=True, slots=True)
class _ParsedSessionRoute:
    channel: str
    peer_id: str
    thread_id: str


def _parse_session_route(session_key: str) -> _ParsedSessionRoute:
    normalized = str(session_key or "").strip()
    if ":" not in normalized:
        return _ParsedSessionRoute("", "", "")
    channel, remainder = normalized.split(":", 1)
    route_head = remainder.split("::", 1)[0]
    peer_id = route_head
    thread_id = ""
    if _TOPIC_MARKER in route_head:
        peer_id, thread_id = route_head.split(_TOPIC_MARKER, 1)
    return _ParsedSessionRoute(channel=channel.strip().lower(), peer_id=peer_id.strip(), thread_id=thread_id.strip())


def _now_iso() -> str:
    return datetime.now().isoformat()


def _record_payload(record: SessionRecord, **overrides: Any) -> dict[str, Any]:
    snapshot = record.as_snapshot()
    snapshot.pop("binding_key", None)
    snapshot.update(overrides)
    return snapshot
