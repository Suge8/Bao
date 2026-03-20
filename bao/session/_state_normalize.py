from __future__ import annotations

from typing import Any, Mapping

from ._state_models import (
    CANONICAL_GROUP_KEYS,
    CHILD_OUTCOME_METADATA_KEYS,
    READ_RECEIPT_METADATA_KEYS,
    ROUTING_METADATA_KEYS,
    RUNTIME_METADATA_KEYS,
    RUNTIME_STATUS_RUNNING,
    VIEW_METADATA_KEYS,
    WORKFLOW_METADATA_KEYS,
    SessionRuntimeState,
)


def _metadata_dict(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(metadata) if isinstance(metadata, Mapping) else {}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def normalize_runtime_metadata(
    runtime_updates: Mapping[str, Any] | SessionRuntimeState | None,
) -> SessionRuntimeState:
    if isinstance(runtime_updates, SessionRuntimeState):
        child_status = runtime_updates.child_status
        is_running = child_status == RUNTIME_STATUS_RUNNING
        return SessionRuntimeState(
            session_running=bool(runtime_updates.session_running),
            child_status=RUNTIME_STATUS_RUNNING if is_running else "",
            active_task_id=str(runtime_updates.active_task_id or "") if is_running else "",
        )
    payload = _metadata_dict(runtime_updates)
    child_running = bool(payload.get("child_running", False))
    child_status = str(payload.get("child_status") or "")
    if child_status != RUNTIME_STATUS_RUNNING and child_running:
        child_status = RUNTIME_STATUS_RUNNING
    if child_status != RUNTIME_STATUS_RUNNING:
        child_status = ""
    return SessionRuntimeState(
        session_running=bool(payload.get("session_running", False)),
        child_status=child_status,
        active_task_id=str(payload.get("active_task_id") or "") if child_status else "",
    )


def nest_flat_persisted_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = _metadata_dict(metadata)
    other = {
        key: value
        for key, value in payload.items()
        if key not in RUNTIME_METADATA_KEYS
        and key not in ROUTING_METADATA_KEYS
        and key not in WORKFLOW_METADATA_KEYS
        and key not in CHILD_OUTCOME_METADATA_KEYS
        and key not in READ_RECEIPT_METADATA_KEYS
        and key not in VIEW_METADATA_KEYS
        and key not in CANONICAL_GROUP_KEYS
    }
    child_status = str(payload.get("child_status") or "")
    return {
        **other,
        "routing": {
            "session_kind": str(payload.get("session_kind") or "regular"),
            "read_only": bool(payload.get("read_only", False)),
            "parent_session_key": str(payload.get("parent_session_key") or ""),
        },
        "workflow": {
            "coding_sessions": payload.get("coding_sessions"),
            "_plan_state": payload.get("_plan_state"),
            "_plan_archived": payload.get("_plan_archived"),
            "_session_lang": str(payload.get("_session_lang") or ""),
            "child_outcome": {
                "status": "" if child_status == RUNTIME_STATUS_RUNNING else child_status,
                "task_label": str(payload.get("task_label") or ""),
                "last_result_summary": str(payload.get("last_result_summary") or ""),
            },
        },
        "view": {
            "title": str(payload.get("title") or ""),
            "read_receipts": {
                "last_ai_at": str(payload.get("desktop_last_ai_at") or ""),
                "last_seen_ai_at": str(payload.get("desktop_last_seen_ai_at") or ""),
            },
        },
    }


def canonicalize_persisted_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = _metadata_dict(metadata)
    routing_payload = _mapping(payload.get("routing"))
    workflow_payload = _mapping(payload.get("workflow"))
    view_payload = _mapping(payload.get("view"))
    child_outcome_payload = _mapping(workflow_payload.get("child_outcome"))
    read_receipts_payload = _mapping(view_payload.get("read_receipts"))
    if "child_outcome" not in workflow_payload:
        workflow_payload["child_outcome"] = child_outcome_payload
    if "read_receipts" not in view_payload:
        view_payload["read_receipts"] = read_receipts_payload
    other = {
        key: value
        for key, value in payload.items()
        if key not in RUNTIME_METADATA_KEYS
        and key not in ROUTING_METADATA_KEYS
        and key not in WORKFLOW_METADATA_KEYS
        and key not in CHILD_OUTCOME_METADATA_KEYS
        and key not in READ_RECEIPT_METADATA_KEYS
        and key not in VIEW_METADATA_KEYS
        and key not in CANONICAL_GROUP_KEYS
    }
    return {
        **other,
        "routing": {
            "session_kind": str(routing_payload.get("session_kind") or "regular"),
            "read_only": bool(routing_payload.get("read_only", False)),
            "parent_session_key": str(routing_payload.get("parent_session_key") or ""),
        },
        "workflow": {
            "coding_sessions": workflow_payload.get("coding_sessions"),
            "_plan_state": workflow_payload.get("_plan_state"),
            "_plan_archived": workflow_payload.get("_plan_archived"),
            "_session_lang": str(workflow_payload.get("_session_lang") or ""),
            "child_outcome": {
                "status": str(child_outcome_payload.get("status") or ""),
                "task_label": str(child_outcome_payload.get("task_label") or ""),
                "last_result_summary": str(child_outcome_payload.get("last_result_summary") or ""),
            },
        },
        "view": {
            "title": str(view_payload.get("title") or ""),
            "read_receipts": {
                "last_ai_at": str(read_receipts_payload.get("last_ai_at") or ""),
                "last_seen_ai_at": str(read_receipts_payload.get("last_seen_ai_at") or ""),
            },
        },
    }


def flatten_persisted_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    canonical = canonicalize_persisted_metadata(metadata)
    routing = _mapping(canonical.get("routing"))
    workflow = _mapping(canonical.get("workflow"))
    child_outcome = _mapping(workflow.get("child_outcome"))
    view = _mapping(canonical.get("view"))
    read_receipts = _mapping(view.get("read_receipts"))
    other = {key: value for key, value in canonical.items() if key not in CANONICAL_GROUP_KEYS}
    return {
        **other,
        "session_kind": str(routing.get("session_kind") or "regular"),
        "read_only": bool(routing.get("read_only", False)),
        "parent_session_key": str(routing.get("parent_session_key") or ""),
        "coding_sessions": workflow.get("coding_sessions"),
        "_plan_state": workflow.get("_plan_state"),
        "_plan_archived": workflow.get("_plan_archived"),
        "_session_lang": str(workflow.get("_session_lang") or ""),
        "child_status": str(child_outcome.get("status") or ""),
        "task_label": str(child_outcome.get("task_label") or ""),
        "last_result_summary": str(child_outcome.get("last_result_summary") or ""),
        "title": str(view.get("title") or ""),
        "desktop_last_ai_at": str(read_receipts.get("last_ai_at") or ""),
        "desktop_last_seen_ai_at": str(read_receipts.get("last_seen_ai_at") or ""),
    }


def split_runtime_metadata(
    metadata: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], SessionRuntimeState]:
    persisted = _metadata_dict(metadata)
    session_running = bool(persisted.pop("session_running", False))
    child_status = str(persisted.get("child_status") or "")
    active_task_id = str(persisted.pop("active_task_id", "") or "")
    runtime = SessionRuntimeState(session_running=session_running)
    if child_status == RUNTIME_STATUS_RUNNING:
        persisted.pop("child_status", None)
        runtime = SessionRuntimeState(
            session_running=session_running,
            child_status=RUNTIME_STATUS_RUNNING,
            active_task_id=active_task_id,
        )
    return persisted, runtime


def merge_runtime_metadata(
    metadata: Mapping[str, Any] | None,
    runtime_updates: Mapping[str, Any] | SessionRuntimeState | None,
) -> dict[str, Any]:
    merged = _metadata_dict(metadata)
    runtime = normalize_runtime_metadata(runtime_updates)
    merged.update(runtime.to_metadata())
    return merged


def filter_persisted_metadata_updates(metadata_updates: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        field: value
        for field, value in _metadata_dict(metadata_updates).items()
        if field not in RUNTIME_METADATA_KEYS
    }
