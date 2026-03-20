from __future__ import annotations

from pathlib import Path

from bao.session.manager import SessionManager


def _save_session(manager: SessionManager, key: str, *, parent_session_key: str = "") -> None:
    session = manager.get_or_create(key)
    if parent_session_key:
        session.metadata["parent_session_key"] = parent_session_key
    session.add_message("assistant", key)
    manager.save(session)


def test_delete_session_tree_removes_all_descendants(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    _save_session(manager, "desktop:local::parent")
    _save_session(
        manager,
        "subagent:desktop:local::parent::child-1",
        parent_session_key="desktop:local::parent",
    )
    _save_session(
        manager,
        "subagent:desktop:local::parent::child-2",
        parent_session_key="desktop:local::parent",
    )
    _save_session(
        manager,
        "subagent:subagent:desktop:local::parent::child-1::grandchild",
        parent_session_key="subagent:desktop:local::parent::child-1",
    )

    assert manager.delete_session_tree("desktop:local::parent") is True
    assert manager.list_sessions() == []
