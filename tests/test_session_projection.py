from app.backend.session_projection import (
    build_sidebar_projection,
    normalize_session_items,
    project_session_item,
)


def test_project_session_item_tracks_child_route_and_running_state() -> None:
    parent = {
        "key": "desktop:local::main",
        "title": "Main",
        "channel": "desktop",
        "updated_at": "2026-03-14T10:00:00",
    }
    child = {
        "key": "subagent:desktop:local::main::child-1",
        "updated_at": "2026-03-14T10:01:00",
        "routing": {
            "session_kind": "subagent_child",
            "read_only": True,
            "parent_session_key": "desktop:local::main",
        },
        "runtime": {
            "session_running": False,
            "child_running": True,
            "active_task_id": "task-1",
            "is_running": True,
        },
        "workflow": {
            "coding_sessions": None,
            "_plan_state": None,
            "_plan_archived": None,
            "_session_lang": "",
            "child_outcome": {
                "status": "",
                "task_label": "child",
                "last_result_summary": "",
            },
        },
        "view": {
            "title": "child",
            "read_receipts": {
                "last_ai_at": "",
                "last_seen_ai_at": "",
                "has_unread_ai": False,
            },
        },
        "message_count": 3,
        "has_messages": True,
    }

    projected = project_session_item(
        child,
        natural_key="desktop:local",
        current_sessions=[parent],
    )

    assert projected["channel"] == "desktop"
    assert projected["parent_title"] == "Main"
    assert projected["is_running"] is True
    assert projected["is_read_only"] is True


def test_project_session_item_prefers_structured_snapshot_fields() -> None:
    parent = {
        "key": "desktop:local::main",
        "title": "Main",
        "channel": "desktop",
        "updated_at": "2026-03-14T10:00:00",
    }
    child = {
        "key": "subagent:desktop:local::main::child-1",
        "updated_at": "2026-03-14T10:01:00",
        "metadata": {},
        "routing": {
            "session_kind": "subagent_child",
            "read_only": True,
            "parent_session_key": "desktop:local::main",
        },
        "runtime": {
            "session_running": False,
            "child_running": True,
            "active_task_id": "task-1",
            "is_running": True,
        },
        "workflow": {
            "coding_sessions": None,
            "_plan_state": None,
            "_plan_archived": None,
            "_session_lang": "",
            "child_outcome": {
                "status": "",
                "task_label": "structured child",
                "last_result_summary": "",
            },
        },
        "view": {
            "title": "structured child",
            "read_receipts": {
                "last_ai_at": "2026-03-14T10:01:00",
                "last_seen_ai_at": "2026-03-14T10:00:00",
                "has_unread_ai": True,
            },
        },
        "message_count": 3,
        "has_messages": True,
    }

    projected = project_session_item(
        child,
        natural_key="desktop:local",
        current_sessions=[parent],
    )

    assert projected["title"] == "structured child"
    assert projected["has_unread"] is True
    assert projected["channel"] == "desktop"
    assert projected["parent_title"] == "Main"
    assert projected["is_running"] is True
    assert projected["is_read_only"] is True


def test_sidebar_projection_keeps_parent_running_and_active_row_visible() -> None:
    sessions = normalize_session_items(
        [
            {
                "key": "desktop:local::main",
                "title": "Main",
                "updated_at": "2026-03-14T10:00:00",
                "channel": "desktop",
                "has_unread": False,
                "session_kind": "regular",
                "is_read_only": False,
                "parent_session_key": "",
                "parent_title": "",
                "child_status": "",
                "is_running": False,
                "self_running": False,
            },
            {
                "key": "subagent:desktop:local::main::child-1",
                "title": "Child",
                "updated_at": "2026-03-14T10:01:00",
                "channel": "desktop",
                "has_unread": True,
                "session_kind": "subagent_child",
                "is_read_only": True,
                "parent_session_key": "desktop:local::main",
                "parent_title": "",
                "child_status": "running",
                "is_running": True,
                "self_running": True,
            },
        ]
    )

    projection = build_sidebar_projection(
        sessions,
        active_key="desktop:local::main",
        expanded_groups={"desktop": False},
    )

    assert projection.unread_count == 1
    assert projection.rows[0]["is_header"] is True
    assert any(row.get("item_key") == "desktop:local::main" for row in projection.rows)
    parent = next(row for row in sessions if row["key"] == "desktop:local::main")
    assert parent["is_running"] is True
