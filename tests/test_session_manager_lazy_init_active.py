from __future__ import annotations

import threading
from pathlib import Path

from bao.session.manager import MarkDesktopSeenRequest, SessionManager
from tests._session_manager_lazy_init_testkit import _list_sessions_while_meta_delete_is_blocked


def test_resolve_active_session_key_prefers_existing_family_sibling(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    sm.save(sm.get_or_create("imessage:+8618127419003"))
    sm.save(sm.get_or_create("imessage:+8618127419003::s7"))
    sm.set_active_session_key("imessage:+8618127419003", "imessage:+8618127419003::s7")

    assert sm.resolve_active_session_key("imessage:+8618127419003") == "imessage:+8618127419003::s7"


def test_resolve_active_session_key_falls_back_to_natural_key_when_active_missing(
    tmp_path: Path,
) -> None:
    sm = SessionManager(tmp_path)
    sm.save(sm.get_or_create("imessage:+8618127419003"))
    sm.set_active_session_key("imessage:+8618127419003", "imessage:+8618127419003::stale")

    assert sm.resolve_active_session_key("imessage:+8618127419003") == "imessage:+8618127419003"


def test_resolve_active_session_key_ignores_desktop_active_marker(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    sm.save(sm.get_or_create("desktop:local::viewing"))
    sm.save(sm.get_or_create("imessage:+8618127419003::s7"))
    sm.set_active_session_key("desktop:local", "imessage:+8618127419003::s7")

    assert sm.resolve_active_session_key("imessage:+8618127419003") == "imessage:+8618127419003"


def test_mark_desktop_seen_ai_if_active_updates_seen_timestamp(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    session = sm.get_or_create("imessage:+8618127419003::s7")
    session.add_message("assistant", "hello")
    sm.save(session)
    sm.set_active_session_key("desktop:local", "imessage:+8618127419003::s7")

    sm.mark_desktop_seen_ai_if_active("imessage:+8618127419003::s7")

    reloaded = sm.get_or_create("imessage:+8618127419003::s7")
    assert isinstance(reloaded.metadata.get("desktop_last_seen_ai_at"), str)


def test_mark_desktop_seen_ai_clears_running_before_visible_metadata_refresh(
    tmp_path: Path,
) -> None:
    sm = SessionManager(tmp_path)
    key = "imessage:+8618127419003::s7"
    session = sm.get_or_create(key)
    session.add_message("assistant", "hello")
    sm.save(session)
    sm.set_session_running(key, True, emit_change=False)

    update_thread = threading.Thread(
        target=lambda: sm.mark_desktop_seen_ai(key, MarkDesktopSeenRequest(clear_running=True)),
        daemon=True,
    )

    listed_sessions = _list_sessions_while_meta_delete_is_blocked(sm, key, update_thread)

    assert [item["key"] for item in listed_sessions] == [key]
    assert isinstance(
        listed_sessions[0]["metadata"]["view"]["read_receipts"]["last_seen_ai_at"],
        str,
    )
    assert listed_sessions[0]["metadata"].get("session_running") is None


def test_mark_desktop_seen_ai_emits_single_metadata_change(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "imessage:+8618127419003::s7"
    session = sm.get_or_create(key)
    session.add_message("assistant", "hello")
    sm.save(session)
    sm.set_session_running(key, True, emit_change=False)
    events: list[tuple[str, str]] = []
    sm.add_change_listener(lambda event: events.append((event.session_key, event.kind)))

    sm.mark_desktop_seen_ai(key, MarkDesktopSeenRequest(clear_running=True))

    assert events == [(key, "metadata")]


def test_mark_desktop_turn_completed_clears_running_and_marks_seen(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "imessage:+8618127419003::s7"
    session = sm.get_or_create(key)
    session.add_message("assistant", "hello")
    sm.save(session)
    sm.set_session_running(key, True, emit_change=False)

    sm.mark_desktop_turn_completed(key, emit_change=False)

    listed = {item["key"]: item for item in sm.list_sessions()}
    assert listed[key]["metadata"].get("session_running") is None
    assert isinstance(listed[key]["metadata"]["view"]["read_receipts"].get("last_seen_ai_at"), str)


def test_list_sessions_with_active_key_returns_combined_snapshot(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    first = sm.get_or_create("desktop:local::first")
    first.metadata["title"] = "First"
    sm.save(first)

    second = sm.get_or_create("desktop:local::second")
    second.metadata["title"] = "Second"
    sm.save(second)

    sm.set_active_session_key("desktop:local", "desktop:local::second")

    sessions, active_key = sm.list_sessions_with_active_key("desktop:local")

    assert active_key == "desktop:local::second"
    assert [item["key"] for item in sessions] == [
        "desktop:local::second",
        "desktop:local::first",
    ]


def test_mark_desktop_seen_ai_if_active_ignores_inactive_session(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    session = sm.get_or_create("imessage:+8618127419003::s7")
    session.add_message("assistant", "hello")
    sm.save(session)
    sm.set_active_session_key("desktop:local", "desktop:local::main")

    sm.mark_desktop_seen_ai_if_active("imessage:+8618127419003::s7")

    reloaded = sm.get_or_create("imessage:+8618127419003::s7")
    assert reloaded.metadata.get("desktop_last_seen_ai_at") in (None, "")
