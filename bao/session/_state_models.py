from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RUNTIME_STATUS_RUNNING = "running"
RUNTIME_METADATA_KEYS = frozenset({"session_running", "child_status", "active_task_id"})
SESSION_ACTIVITY_SESSION_STARTED = "session_started"
SESSION_ACTIVITY_SESSION_FINISHED = "session_finished"
SESSION_ACTIVITY_CHILD_STARTED = "child_started"
SESSION_ACTIVITY_CHILD_CLEARED = "child_cleared"
CHILD_OUTCOME_METADATA_KEYS = frozenset({"child_status", "last_result_summary", "task_label"})
WORKFLOW_METADATA_KEYS = frozenset({"coding_sessions", "_plan_state", "_plan_archived", "_session_lang"})
ROUTING_METADATA_KEYS = frozenset({"session_kind", "read_only", "parent_session_key"})
READ_RECEIPT_METADATA_KEYS = frozenset({"desktop_last_ai_at", "desktop_last_seen_ai_at"})
VIEW_METADATA_KEYS = frozenset({"title"})
CANONICAL_GROUP_KEYS = frozenset({"routing", "workflow", "view"})


@dataclass(frozen=True)
class SessionRuntimeState:
    session_running: bool = False
    child_status: str = ""
    active_task_id: str = ""

    @property
    def child_running(self) -> bool:
        return self.child_status == RUNTIME_STATUS_RUNNING

    @property
    def is_running(self) -> bool:
        return self.session_running or self.child_running

    def to_metadata(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.session_running:
            payload["session_running"] = True
        if self.child_running:
            payload["child_status"] = RUNTIME_STATUS_RUNNING
            if self.active_task_id:
                payload["active_task_id"] = self.active_task_id
        return payload

    def as_snapshot(self) -> dict[str, Any]:
        return {
            "session_running": self.session_running,
            "child_running": self.child_running,
            "active_task_id": self.active_task_id,
            "is_running": self.is_running,
        }


@dataclass(frozen=True)
class SessionRoutingMetadata:
    session_kind: str = "regular"
    read_only: bool = False
    parent_session_key: str = ""

    def as_snapshot(self) -> dict[str, Any]:
        return {
            "session_kind": self.session_kind,
            "read_only": self.read_only,
            "parent_session_key": self.parent_session_key,
        }


@dataclass(frozen=True)
class SessionChildOutcome:
    status: str = ""
    task_label: str = ""
    last_result_summary: str = ""

    def as_snapshot(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "task_label": self.task_label,
            "last_result_summary": self.last_result_summary,
        }


@dataclass(frozen=True)
class SessionWorkflowState:
    coding_sessions: Any = None
    plan_state: Any = None
    plan_archived: Any = None
    session_lang: str = ""
    child_outcome: SessionChildOutcome = field(default_factory=SessionChildOutcome)

    def as_snapshot(self) -> dict[str, Any]:
        return {
            "coding_sessions": self.coding_sessions,
            "_plan_state": self.plan_state,
            "_plan_archived": self.plan_archived,
            "_session_lang": self.session_lang,
            "child_outcome": self.child_outcome.as_snapshot(),
        }


@dataclass(frozen=True)
class SessionReadReceiptState:
    last_ai_at: str = ""
    last_seen_ai_at: str = ""

    @property
    def has_unread_ai(self) -> bool:
        if not self.last_ai_at:
            return False
        seen_at = self.last_seen_ai_at or self.last_ai_at
        return seen_at < self.last_ai_at

    def as_snapshot(self) -> dict[str, Any]:
        return {
            "last_ai_at": self.last_ai_at,
            "last_seen_ai_at": self.last_seen_ai_at,
            "has_unread_ai": self.has_unread_ai,
        }


@dataclass(frozen=True)
class SessionViewState:
    title: str = ""
    read_receipts: SessionReadReceiptState = field(default_factory=SessionReadReceiptState)

    def as_snapshot(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "read_receipts": self.read_receipts.as_snapshot(),
        }


@dataclass(frozen=True)
class SessionSnapshot:
    metadata: dict[str, Any]
    routing: SessionRoutingMetadata
    runtime: SessionRuntimeState
    workflow: SessionWorkflowState
    view: SessionViewState


SessionActivityKind = Literal[
    "session_started",
    "session_finished",
    "child_started",
    "child_cleared",
]


@dataclass(frozen=True)
class SessionActivityEvent:
    kind: SessionActivityKind
    task_id: str = ""
