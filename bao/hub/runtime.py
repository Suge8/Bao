from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .directory import HubDirectory


@dataclass(frozen=True, slots=True)
class HubPersistMessageRequest:
    session_key: str
    role: str
    content: str
    status: str = "done"
    format: str = ""
    entrance_style: str = ""
    source: str = ""
    emit_change: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HubUserMessageStatusRequest:
    session_key: str
    token: str
    status: str
    emit_change: bool = False


@dataclass(frozen=True, slots=True)
class HubRunningStateRequest:
    session_key: str
    is_running: bool
    emit_change: bool = True


@dataclass(frozen=True, slots=True)
class HubSeenRequest:
    session_key: str
    emit_change: bool = False
    metadata_updates: dict[str, Any] = field(default_factory=dict)
    clear_running: bool = False


class HubRuntimePort:
    """Runtime-bound transcript/state write port."""

    def __init__(self, session_manager: Any) -> None:
        self._session_manager = session_manager
        self._directory = HubDirectory(session_manager)

    @property
    def session_manager(self) -> Any:
        return self._session_manager

    @property
    def directory(self) -> HubDirectory:
        return self._directory

    @property
    def workspace(self) -> Path | None:
        workspace = getattr(self._session_manager, "workspace", None)
        if not isinstance(workspace, (str, Path)):
            return None
        return Path(str(workspace)).expanduser()

    def add_change_listener(self, listener: Any) -> None:
        self._directory.add_change_listener(listener)

    def remove_change_listener(self, listener: Any) -> None:
        self._directory.remove_change_listener(listener)

    def persist_message(self, request: HubPersistMessageRequest) -> None:
        session = self._session_manager.get_or_create(request.session_key)
        message_kwargs: dict[str, Any] = {"status": request.status}
        if request.format:
            message_kwargs["format"] = request.format
        if request.entrance_style:
            message_kwargs["entrance_style"] = request.entrance_style
        if request.source:
            message_kwargs["_source"] = request.source
        if request.metadata:
            message_kwargs.update(dict(request.metadata))
        session.add_message(request.role, request.content, **message_kwargs)
        self._session_manager.save(session, emit_change=request.emit_change)

    def update_user_message_status(self, request: HubUserMessageStatusRequest) -> None:
        session = self._session_manager.get_or_create(request.session_key)
        for message in reversed(session.messages):
            if message.get("role") != "user":
                continue
            if message.get("_pre_saved_token") != request.token:
                continue
            message["status"] = request.status
            session.updated_at = datetime.now()
            self._session_manager.save(session, emit_change=request.emit_change)
            return

    def set_session_running(self, request: HubRunningStateRequest) -> None:
        self._session_manager.set_session_running(
            request.session_key,
            bool(request.is_running),
            emit_change=request.emit_change,
        )

    def mark_seen(self, request: HubSeenRequest) -> None:
        mark_completed = getattr(self._session_manager, "mark_desktop_turn_completed", None)
        if request.clear_running and callable(mark_completed):
            mark_completed(
                request.session_key,
                emit_change=request.emit_change,
                metadata_updates=request.metadata_updates or None,
            )
            return
        self._session_manager.mark_desktop_seen_ai(
            request.session_key,
            emit_change=request.emit_change,
            metadata_updates=request.metadata_updates or None,
            clear_running=request.clear_running,
        )
