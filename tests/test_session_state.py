from bao.session.state import (
    RUNTIME_STATUS_RUNNING,
    SESSION_ACTIVITY_CHILD_CLEARED,
    SESSION_ACTIVITY_CHILD_STARTED,
    SESSION_ACTIVITY_SESSION_FINISHED,
    SESSION_ACTIVITY_SESSION_STARTED,
    SessionActivityEvent,
    apply_runtime_activity,
    build_session_snapshot,
    canonicalize_persisted_metadata,
    desktop_has_unread_ai,
    filter_persisted_metadata_updates,
    flatten_persisted_metadata,
    merge_runtime_metadata,
    nest_flat_persisted_metadata,
    session_metadata_group,
    session_routing_metadata,
    split_runtime_metadata,
)


def _runtime_metadata_fixture() -> dict[str, object]:
    return {
        "title": "default",
        "desktop_last_ai_at": "2026-03-14T10:00:00",
        "desktop_last_seen_ai_at": "2026-03-14T09:00:00",
        "session_kind": "subagent_child",
        "read_only": True,
        "parent_session_key": "desktop:local::main",
        "_plan_state": {"goal": "ship"},
        "session_running": True,
    }


def _assert_persisted_helper_outputs(
    metadata: dict[str, object],
    runtime_metadata: dict[str, object],
) -> None:
    assert desktop_has_unread_ai(metadata) is True
    assert filter_persisted_metadata_updates(runtime_metadata) == {
        "title": "default",
        "desktop_last_ai_at": "2026-03-14T10:00:00",
        "desktop_last_seen_ai_at": "2026-03-14T09:00:00",
        "session_kind": "subagent_child",
        "read_only": True,
        "parent_session_key": "desktop:local::main",
        "_plan_state": {"goal": "ship"},
    }
    assert merge_runtime_metadata({"title": "default"}, {"session_running": True}) == {
        "title": "default",
        "session_running": True,
    }
    assert session_routing_metadata(metadata).parent_session_key == "desktop:local::main"
    assert session_metadata_group(metadata, "workflow") == {
        "coding_sessions": None,
        "_plan_state": {"goal": "ship"},
        "_plan_archived": None,
        "_session_lang": "",
        "child_outcome": {
            "status": "",
            "task_label": "",
            "last_result_summary": "",
        },
    }
    assert session_metadata_group(metadata, "view") == {
        "title": "default",
        "read_receipts": {
            "last_ai_at": "2026-03-14T10:00:00",
            "last_seen_ai_at": "2026-03-14T09:00:00",
            "has_unread_ai": True,
        },
    }


def _assert_session_snapshot(snapshot) -> None:
    assert snapshot.routing.as_snapshot() == {
        "session_kind": "subagent_child",
        "read_only": True,
        "parent_session_key": "desktop:local::main",
    }
    assert snapshot.workflow.as_snapshot()["child_outcome"] == {
        "status": "",
        "task_label": "",
        "last_result_summary": "",
    }
    assert snapshot.view.as_snapshot()["read_receipts"] == {
        "last_ai_at": "2026-03-14T10:00:00",
        "last_seen_ai_at": "2026-03-14T09:00:00",
        "has_unread_ai": True,
    }


def test_split_runtime_metadata_strips_only_running_overlay() -> None:
    persisted, runtime = split_runtime_metadata(
        {
            "title": "main",
            "session_running": True,
            "child_status": RUNTIME_STATUS_RUNNING,
            "active_task_id": "task-1",
        }
    )

    assert persisted == {"title": "main"}
    assert runtime.to_metadata() == {
        "session_running": True,
        "child_status": RUNTIME_STATUS_RUNNING,
        "active_task_id": "task-1",
    }

    persisted_done, runtime_done = split_runtime_metadata(
        {"child_status": "completed", "active_task_id": "task-2"}
    )
    assert persisted_done == {"child_status": "completed"}
    assert runtime_done.to_metadata() == {}


def test_state_helpers_preserve_routing_and_persisted_groups() -> None:
    runtime_metadata = _runtime_metadata_fixture()
    metadata = nest_flat_persisted_metadata(runtime_metadata)

    _assert_persisted_helper_outputs(metadata, runtime_metadata)

    snapshot = build_session_snapshot(metadata)
    _assert_session_snapshot(snapshot)
    assert flatten_persisted_metadata(metadata)["title"] == "default"


def test_canonicalize_persisted_metadata_ignores_legacy_flat_fields() -> None:
    metadata = canonicalize_persisted_metadata(
        {
            "title": "legacy",
            "desktop_last_ai_at": "2026-03-14T10:00:00",
            "routing": {"session_kind": "regular"},
        }
    )

    assert metadata["routing"] == {
        "session_kind": "regular",
        "read_only": False,
        "parent_session_key": "",
    }
    assert metadata["view"] == {
        "title": "",
        "read_receipts": {
            "last_ai_at": "",
            "last_seen_ai_at": "",
        },
    }


def test_apply_runtime_activity_updates_snapshot_without_persisted_status() -> None:
    runtime = apply_runtime_activity(
        None,
        SessionActivityEvent(kind=SESSION_ACTIVITY_SESSION_STARTED),
    )
    assert runtime.to_metadata() == {"session_running": True}

    child_runtime = apply_runtime_activity(
        runtime,
        SessionActivityEvent(kind=SESSION_ACTIVITY_CHILD_STARTED, task_id="task-1"),
    )
    assert child_runtime.to_metadata() == {
        "session_running": True,
        "child_status": RUNTIME_STATUS_RUNNING,
        "active_task_id": "task-1",
    }

    cleared_child = apply_runtime_activity(
        child_runtime,
        SessionActivityEvent(kind=SESSION_ACTIVITY_CHILD_CLEARED),
    )
    assert cleared_child.to_metadata() == {"session_running": True}

    stopped = apply_runtime_activity(
        cleared_child,
        SessionActivityEvent(kind=SESSION_ACTIVITY_SESSION_FINISHED),
    )
    assert stopped.to_metadata() == {}
