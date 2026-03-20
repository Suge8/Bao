from __future__ import annotations

import threading
from pathlib import Path

from bao.session.manager import SessionManager
from tests._session_manager_lazy_init_testkit import _list_sessions_while_meta_delete_is_blocked


def test_list_sessions_waits_for_inflight_save_metadata_rewrite(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "imessage:chat-1"
    session = sm.get_or_create(key)
    session.add_message("assistant", "before")
    sm.save(session)

    session.metadata["title"] = "updated"
    save_thread = threading.Thread(target=lambda: sm.save(session), daemon=True)

    listed_sessions = _list_sessions_while_meta_delete_is_blocked(sm, key, save_thread)

    assert [item["key"] for item in listed_sessions] == [key]
    assert listed_sessions[0]["metadata"]["view"]["title"] == "updated"


def test_list_sessions_waits_for_inflight_metadata_only_rewrite(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "telegram:room-1"
    session = sm.get_or_create(key)
    session.add_message("assistant", "hello")
    sm.save(session)

    update_thread = threading.Thread(
        target=lambda: sm.update_metadata_only(
            key, {"desktop_last_seen_ai_at": "2026-01-01T00:00:00"}
        ),
        daemon=True,
    )

    listed_sessions = _list_sessions_while_meta_delete_is_blocked(sm, key, update_thread)

    assert [item["key"] for item in listed_sessions] == [key]
    assert (
        listed_sessions[0]["metadata"]["view"]["read_receipts"]["last_seen_ai_at"]
        == "2026-01-01T00:00:00"
    )


def test_update_metadata_only_keyword_path_uses_same_meta_barrier(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "qq:room-kw"
    session = sm.get_or_create(key)
    session.add_message("assistant", "hello")
    sm.save(session)

    update_thread = threading.Thread(
        target=lambda: sm.update_metadata_only(
            key=key,
            metadata_updates={"desktop_last_seen_ai_at": "2026-01-02T00:00:00"},
        ),
        daemon=True,
    )

    listed_sessions = _list_sessions_while_meta_delete_is_blocked(sm, key, update_thread)

    assert [item["key"] for item in listed_sessions] == [key]
    assert (
        listed_sessions[0]["metadata"]["view"]["read_receipts"]["last_seen_ai_at"]
        == "2026-01-02T00:00:00"
    )
