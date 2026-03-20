from __future__ import annotations

from typing import Any, Mapping

from ._state_models import (
    CANONICAL_GROUP_KEYS,
    RUNTIME_STATUS_RUNNING,
    SESSION_ACTIVITY_CHILD_CLEARED,
    SESSION_ACTIVITY_CHILD_STARTED,
    SESSION_ACTIVITY_SESSION_FINISHED,
    SESSION_ACTIVITY_SESSION_STARTED,
    SessionActivityEvent,
    SessionChildOutcome,
    SessionReadReceiptState,
    SessionRoutingMetadata,
    SessionRuntimeState,
    SessionSnapshot,
    SessionViewState,
    SessionWorkflowState,
)
from ._state_normalize import (
    _mapping,
    _metadata_dict,
    canonicalize_persisted_metadata,
    flatten_persisted_metadata,
    merge_runtime_metadata,
    normalize_runtime_metadata,
)


def build_session_snapshot(
    metadata: Mapping[str, Any] | None,
    *,
    runtime_updates: Mapping[str, Any] | SessionRuntimeState | None = None,
) -> SessionSnapshot:
    canonical = canonicalize_persisted_metadata(metadata)
    merged = merge_runtime_metadata(flatten_persisted_metadata(canonical), runtime_updates)
    return SessionSnapshot(
        metadata=merged,
        routing=session_routing_metadata(canonical),
        runtime=session_runtime_state(merged),
        workflow=session_workflow_state(canonical),
        view=session_view_state(canonical),
    )


def apply_runtime_activity(
    runtime: Mapping[str, Any] | SessionRuntimeState | None,
    activity: SessionActivityEvent,
) -> SessionRuntimeState:
    current = normalize_runtime_metadata(runtime)
    if activity.kind == SESSION_ACTIVITY_SESSION_STARTED:
        return SessionRuntimeState(True, current.child_status, current.active_task_id)
    if activity.kind == SESSION_ACTIVITY_SESSION_FINISHED:
        active_task_id = current.active_task_id if current.child_status else ""
        return SessionRuntimeState(False, current.child_status, active_task_id)
    if activity.kind == SESSION_ACTIVITY_CHILD_STARTED:
        return SessionRuntimeState(
            session_running=current.session_running,
            child_status=RUNTIME_STATUS_RUNNING,
            active_task_id=str(activity.task_id or "").strip(),
        )
    if activity.kind == SESSION_ACTIVITY_CHILD_CLEARED:
        return SessionRuntimeState(session_running=current.session_running)
    return current


def session_runtime_state(metadata: Mapping[str, Any] | None) -> SessionRuntimeState:
    return normalize_runtime_metadata(metadata)


def session_routing_metadata(metadata: Mapping[str, Any] | None) -> SessionRoutingMetadata:
    payload = _mapping(_metadata_dict(metadata).get("routing"))
    return SessionRoutingMetadata(
        session_kind=str(payload.get("session_kind") or "regular"),
        read_only=bool(payload.get("read_only", False)),
        parent_session_key=str(payload.get("parent_session_key") or ""),
    )


def session_child_outcome(metadata: Mapping[str, Any] | None) -> SessionChildOutcome:
    workflow = _mapping(_metadata_dict(metadata).get("workflow"))
    payload = _mapping(workflow.get("child_outcome"))
    return SessionChildOutcome(
        status=str(payload.get("status") or ""),
        task_label=str(payload.get("task_label") or ""),
        last_result_summary=str(payload.get("last_result_summary") or ""),
    )


def session_workflow_state(metadata: Mapping[str, Any] | None) -> SessionWorkflowState:
    payload = _mapping(_metadata_dict(metadata).get("workflow"))
    return SessionWorkflowState(
        coding_sessions=payload.get("coding_sessions"),
        plan_state=payload.get("_plan_state"),
        plan_archived=payload.get("_plan_archived"),
        session_lang=str(payload.get("_session_lang") or ""),
        child_outcome=session_child_outcome(metadata),
    )


def session_read_receipt_state(metadata: Mapping[str, Any] | None) -> SessionReadReceiptState:
    view = _mapping(_metadata_dict(metadata).get("view"))
    payload = _mapping(view.get("read_receipts"))
    return SessionReadReceiptState(
        last_ai_at=str(payload.get("last_ai_at") or ""),
        last_seen_ai_at=str(payload.get("last_seen_ai_at") or ""),
    )


def session_view_state(metadata: Mapping[str, Any] | None) -> SessionViewState:
    payload = _mapping(_metadata_dict(metadata).get("view"))
    return SessionViewState(
        title=str(payload.get("title") or ""),
        read_receipts=session_read_receipt_state(metadata),
    )


def session_metadata_group(metadata: Mapping[str, Any] | None, group: str) -> dict[str, Any]:
    canonical = canonicalize_persisted_metadata(metadata)
    if group == "runtime":
        return session_runtime_state(canonical).to_metadata()
    if group == "routing":
        return session_routing_metadata(canonical).as_snapshot()
    if group == "workflow":
        workflow = session_workflow_state(canonical)
        return {
            "coding_sessions": workflow.coding_sessions,
            "_plan_state": workflow.plan_state,
            "_plan_archived": workflow.plan_archived,
            "_session_lang": workflow.session_lang,
            "child_outcome": workflow.child_outcome.as_snapshot(),
        }
    if group == "child_outcome":
        return session_child_outcome(canonical).as_snapshot()
    if group == "view":
        return session_view_state(canonical).as_snapshot()
    if group == "read_receipts":
        return session_read_receipt_state(canonical).as_snapshot()
    return {key: value for key, value in canonical.items() if key not in CANONICAL_GROUP_KEYS}


def desktop_has_unread_ai(metadata: Mapping[str, Any] | None) -> bool:
    canonical = canonicalize_persisted_metadata(metadata)
    return session_read_receipt_state(canonical).has_unread_ai
