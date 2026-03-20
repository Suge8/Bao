from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import patch

from bao.session.manager import SessionManager
from tests._session_manager_lazy_init_testkit import pytest


def test_save_fails_when_existing_baseline_cannot_be_loaded(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::baseline-read-fail"
    session = sm.get_or_create(key)
    session.add_message("assistant", "old")
    sm.save(session)
    sm.invalidate(key)

    detached = sm.get_or_create(key)
    delattr(detached, "_persisted_message_fingerprints")
    detached.add_message("assistant", "new")

    msg_tbl = sm._msg_table()
    with patch.object(msg_tbl, "search", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            sm.save(detached)

    sm.invalidate(key)
    reloaded = sm.get_or_create(key)
    assert [msg.get("content") for msg in reloaded.messages] == ["old"]


def test_noop_save_skips_tail_rewrite_and_emits_no_change(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::noop-save"
    events: list[tuple[str, str]] = []
    sm.add_change_listener(lambda event: events.append((event.session_key, event.kind)))

    session = sm.get_or_create(key)
    session.add_message("assistant", "hello")
    sm.save(session)
    events.clear()

    meta_tbl = sm._meta_table()
    msg_tbl = sm._msg_table()
    with (
        patch.object(
            meta_tbl,
            "delete",
            side_effect=AssertionError("noop should not rewrite meta"),
        ),
        patch.object(
            meta_tbl,
            "add",
            side_effect=AssertionError("noop should not rewrite meta"),
        ),
        patch.object(
            sm,
            "_write_display_tail_row",
            side_effect=AssertionError("noop should not rewrite tail"),
        ),
        patch.object(msg_tbl, "search", side_effect=AssertionError("noop should not read rows")),
        patch.object(
            msg_tbl,
            "count_rows",
            side_effect=AssertionError("noop should not count rows"),
        ),
    ):
        sm.save(session)

    assert events == []


def test_metadata_only_save_emits_metadata_without_tail_rewrite(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::metadata-save"
    events: list[tuple[str, str]] = []
    sm.add_change_listener(lambda event: events.append((event.session_key, event.kind)))

    session = sm.get_or_create(key)
    session.add_message("assistant", "hello")
    sm.save(session)
    events.clear()

    session.metadata["foo"] = "bar"
    msg_tbl = sm._msg_table()
    with (
        patch.object(
            sm,
            "_write_display_tail_row",
            side_effect=AssertionError("metadata-only save should not rewrite tail"),
        ),
        patch.object(
            msg_tbl, "search", side_effect=AssertionError("metadata-only save should not read rows")
        ),
        patch.object(
            msg_tbl,
            "count_rows",
            side_effect=AssertionError("metadata-only save should not count rows"),
        ),
    ):
        sm.save(session)

    assert events == [(key, "metadata")]


def test_last_consolidated_change_rewrites_tail_and_emits_messages(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::consolidated-tail"
    events: list[tuple[str, str]] = []
    sm.add_change_listener(lambda event: events.append((event.session_key, event.kind)))

    session = sm.get_or_create(key)
    session.add_message("user", "hello")
    session.add_message("assistant", "world")
    sm.save(session)
    events.clear()

    session.last_consolidated = 1
    sm.save(session)

    assert events == [(key, "messages")]
    sm.invalidate(key)
    reloaded = sm.get_or_create(key)
    assert [msg.get("content") for msg in reloaded.get_display_history()] == ["world"]


def test_failed_clear_save_restores_previous_messages_and_tail(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::rollback-clear"
    session = sm.get_or_create(key)
    session.add_message("assistant", "old")
    sm.save(session)

    session.clear()
    with patch.object(sm, "_write_display_tail_row", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            sm.save(session)

    assert sm.peek_tail_messages(key, 200) is None
    snapshot = sm.get_tail_messages(key, 200)
    assert [msg.get("content") for msg in snapshot] == ["old"]

    sm.invalidate(key)
    reloaded = sm.get_or_create(key)
    assert [msg.get("content") for msg in reloaded.messages] == ["old"]


def test_delete_session_clears_tail_cache(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::delete-cache"
    session = sm.get_or_create(key)
    session.add_message("assistant", "bye")
    sm.save(session)

    assert sm.peek_tail_messages(key, 200) is not None
    assert sm.delete_session(key) is True
    assert sm.peek_tail_messages(key, 200) is None


def test_display_tail_cache_evicts_oldest_sessions(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    for i in range(130):
        key = f"desktop:local::cache-{i}"
        session = sm.get_or_create(key)
        session.add_message("assistant", f"msg-{i}")
        sm.save(session)

    sm._cache.pop("desktop:local::cache-0", None)
    sm._cache.pop("desktop:local::cache-129", None)

    assert sm._display_tail_cache.get("desktop:local::cache-0") is None
    newest = sm.peek_tail_messages("desktop:local::cache-129", 200)
    assert newest is not None
    assert newest[-1]["content"] == "msg-129"


def test_peek_tail_messages_returns_none_when_lock_is_busy(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::busy"
    session = sm.get_or_create(key)
    session.add_message("assistant", "hello")
    sm.save(session)
    sm.invalidate(key)
    sm.get_tail_messages(key, 200)

    lock = sm._lock_for(key)
    ready = threading.Event()
    release = threading.Event()

    def _hold_lock() -> None:
        lock.acquire()
        ready.set()
        release.wait(timeout=2)
        lock.release()

    thread = threading.Thread(target=_hold_lock, daemon=True)
    thread.start()
    assert ready.wait(timeout=2)
    try:
        assert sm.peek_tail_messages(key, 200) is None
    finally:
        release.set()
        thread.join(timeout=2)
