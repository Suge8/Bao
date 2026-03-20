from __future__ import annotations

from pathlib import Path

from bao.session.manager import Session, SessionManager


def test_session_add_message_keeps_runtime_flags_untouched() -> None:
    session = Session(key="imessage:chat-1")
    session.metadata["session_running"] = True

    session.add_message("assistant", "done")

    assert session.metadata["session_running"] is True
    assert isinstance(session.metadata.get("desktop_last_ai_at"), str)


def test_session_add_message_keeps_runtime_flags_for_assistant_progress() -> None:
    session = Session(key="imessage:chat-1")
    session.metadata["session_running"] = True

    session.add_message("assistant", "thinking", _source="assistant-progress")

    assert session.metadata["session_running"] is True
    assert isinstance(session.metadata.get("desktop_last_ai_at"), str)


def test_runtime_running_metadata_is_process_local(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    session = sm.get_or_create("imessage:chat-1::main")
    session.metadata["title"] = "Main"
    sm.save(session)

    sm.set_session_running("imessage:chat-1::main", True, emit_change=False)

    listed = {s["key"]: s for s in sm.list_sessions()}
    assert listed["imessage:chat-1::main"]["metadata"]["session_running"] is True

    reloaded = SessionManager(tmp_path)
    reloaded_sessions = {s["key"]: s for s in reloaded.list_sessions()}
    assert reloaded_sessions["imessage:chat-1::main"]["metadata"].get("session_running") is None


def test_list_sessions_ignores_persisted_running_child_status_after_restart(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    parent = sm.get_or_create("imessage:chat-1::main")
    parent.metadata["title"] = "Main"
    sm.save(parent)

    child = sm.get_or_create("subagent:imessage:chat-1::child")
    child.metadata.update(
        {
            "title": "Child",
            "session_kind": "subagent_child",
            "read_only": True,
            "parent_session_key": "imessage:chat-1::main",
        }
    )
    sm.save(child)

    meta_tbl = sm._meta_table()
    meta_tbl.delete("session_key = 'subagent:imessage:chat-1::child'")
    meta_tbl.add(
        [
            {
                "session_key": "subagent:imessage:chat-1::child",
                "created_at": child.created_at.isoformat(),
                "updated_at": child.updated_at.isoformat(),
                "metadata_json": '{"title":"Child","session_kind":"subagent_child","read_only":true,"parent_session_key":"imessage:chat-1::main","child_status":"running","active_task_id":"task-1"}',
                "last_consolidated": 0,
            }
        ]
    )

    reloaded = SessionManager(tmp_path)
    listed = {s["key"]: s for s in reloaded.list_sessions()}
    child_meta = listed["subagent:imessage:chat-1::child"]["metadata"]
    assert child_meta.get("child_status") is None
    assert child_meta.get("active_task_id") is None


def test_child_running_overlay_is_process_local(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    parent = sm.get_or_create("imessage:chat-1::main")
    parent.metadata["title"] = "Main"
    sm.save(parent)

    child = sm.get_or_create("subagent:imessage:chat-1::child")
    child.metadata.update(
        {
            "title": "Child",
            "session_kind": "subagent_child",
            "read_only": True,
            "parent_session_key": "imessage:chat-1::main",
        }
    )
    sm.save(child)

    sm.set_child_running("subagent:imessage:chat-1::child", "task-1", emit_change=False)

    listed = {s["key"]: s for s in sm.list_sessions()}
    child_meta = listed["subagent:imessage:chat-1::child"]["metadata"]
    assert child_meta["child_status"] == "running"
    assert child_meta["active_task_id"] == "task-1"

    reloaded = SessionManager(tmp_path)
    reloaded_sessions = {s["key"]: s for s in reloaded.list_sessions()}
    reloaded_child_meta = reloaded_sessions["subagent:imessage:chat-1::child"]["metadata"]
    assert reloaded_child_meta.get("child_status") is None
    assert reloaded_child_meta.get("active_task_id") is None


def test_save_preserves_runtime_overlay_until_explicit_clear(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    session = sm.get_or_create("imessage:chat-1::main")
    session.metadata["title"] = "Main"
    sm.save(session)

    sm.set_session_running("imessage:chat-1::main", True, emit_change=False)

    cached = sm.get_or_create("imessage:chat-1::main")
    cached.add_message("assistant", "done")
    sm.save(cached)

    listed = {s["key"]: s for s in sm.list_sessions()}
    assert listed["imessage:chat-1::main"]["metadata"]["session_running"] is True

    sm.set_session_running("imessage:chat-1::main", False, emit_change=False)

    cleared = {s["key"]: s for s in sm.list_sessions()}
    assert cleared["imessage:chat-1::main"]["metadata"].get("session_running") is None
