from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from bao.session.manager import SessionManager
from tests._session_manager_lazy_init_testkit import pytest


def test_save_persists_tail_snapshot_for_background_read(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::cache"
    session = sm.get_or_create(key)
    session.add_message("assistant", "hello")
    sm.save(session)

    cached = sm.peek_tail_messages(key, 200)
    assert cached is not None
    assert cached[-1]["content"] == "hello"

    sm.invalidate(key)

    assert sm.peek_tail_messages(key, 200) is None
    persisted = sm.get_tail_messages(key, 200)
    assert persisted is not None
    assert persisted[-1]["content"] == "hello"


def test_get_tail_messages_backfills_missing_persisted_tail_row(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::legacy"
    session = sm.get_or_create(key)
    session.add_message("assistant", "hello")
    sm.save(session)

    sm._delete_display_tail_row(key)
    sm.invalidate(key)

    assert sm._read_display_tail_row(key) is None
    assert [msg.get("content") for msg in sm.get_tail_messages(key, 200)] == ["hello"]

    sm.invalidate(key)
    assert sm.peek_tail_messages(key, 200) is None
    persisted = sm.get_tail_messages(key, 200)
    assert persisted is not None
    assert [msg.get("content") for msg in persisted] == ["hello"]


def test_empty_session_persists_empty_tail_snapshot(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::empty"
    session = sm.get_or_create(key)
    sm.save(session)

    sm.invalidate(key)

    assert sm.peek_tail_messages(key, 200) is None
    assert sm.get_tail_messages(key, 200) == []


def test_get_tail_messages_backfills_missing_empty_tail_row(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::legacy-empty"
    session = sm.get_or_create(key)
    sm.save(session)

    sm._delete_display_tail_row(key)
    sm.invalidate(key)

    assert sm._read_display_tail_row(key) is None
    assert sm.get_tail_messages(key, 200) == []

    sm.invalidate(key)
    assert sm.peek_tail_messages(key, 200) is None
    assert sm.get_tail_messages(key, 200) == []


def test_display_history_snapshot_preserves_timestamp(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::timestamped"
    session = sm.get_or_create(key)
    session.add_message("assistant", "hello")
    sm.save(session)
    sm.invalidate(key)

    snapshot = sm.get_tail_messages(key, 200)
    assert snapshot is not None
    assert snapshot[-1]["timestamp"]


def test_list_sessions_exposes_message_summary_from_display_tail(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    empty_key = "desktop:local::empty-summary"
    full_key = "desktop:local::full-summary"

    empty_session = sm.get_or_create(empty_key)
    sm.save(empty_session)

    full_session = sm.get_or_create(full_key)
    full_session.add_message("assistant", "hello")
    sm.save(full_session)

    sessions = {item["key"]: item for item in sm.list_sessions()}

    assert sessions[empty_key]["message_count"] == 0
    assert sessions[empty_key]["has_messages"] is False
    assert sessions[full_key]["message_count"] == 1
    assert sessions[full_key]["has_messages"] is True


def test_list_sessions_batches_display_tail_read_model(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    for idx in range(2):
        key = f"desktop:local::batched-{idx}"
        session = sm.get_or_create(key)
        session.add_message("assistant", f"hello-{idx}")
        sm.save(session)
        sm.invalidate(key)

    with patch.object(
        sm,
        "_read_display_tail_row",
        side_effect=AssertionError("list_sessions should use batched tail read model"),
    ):
        sessions = {item["key"]: item for item in sm.list_sessions()}

    assert sessions["desktop:local::batched-0"]["message_count"] == 1
    assert sessions["desktop:local::batched-1"]["message_count"] == 1


def test_list_sessions_marks_missing_display_tail_for_backfill(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::needs-backfill"

    session = sm.get_or_create(key)
    session.add_message("assistant", "hello")
    sm.save(session)

    sm._delete_display_tail_row(key)
    sm.invalidate(key)

    sessions = {item["key"]: item for item in sm.list_sessions()}

    assert sessions[key]["message_count"] is None
    assert sessions[key]["has_messages"] is None
    assert sessions[key]["needs_tail_backfill"] is True


def test_failed_save_does_not_leak_uncommitted_tail_snapshot(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::rollback-tail"
    session = sm.get_or_create(key)
    session.add_message("assistant", "old")
    sm.save(session)

    session.add_message("assistant", "new")
    with patch.object(sm._msg_table(), "add", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            sm.save(session)

    assert sm.peek_tail_messages(key, 200) is None
    snapshot = sm.get_tail_messages(key, 200)
    contents = [msg.get("content") for msg in snapshot]
    assert contents == ["old"]


def test_append_save_skips_msg_table_reads_when_session_snapshot_is_hot(tmp_path: Path) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::append-hot"
    session = sm.get_or_create(key)
    session.add_message("assistant", "old")
    sm.save(session)

    session.add_message("assistant", "new")
    msg_tbl = sm._msg_table()
    with (
        patch.object(
            msg_tbl, "search", side_effect=AssertionError("append path should not read rows")
        ),
        patch.object(
            msg_tbl,
            "count_rows",
            side_effect=AssertionError("append path should not count rows"),
        ),
    ):
        sm.save(session)

    sm.invalidate(key)
    reloaded = sm.get_or_create(key)
    assert [msg.get("content") for msg in reloaded.messages] == ["old", "new"]


def test_append_after_reload_skips_msg_table_reads_when_snapshot_seeded_from_load(
    tmp_path: Path,
) -> None:
    sm = SessionManager(tmp_path)
    key = "desktop:local::append-reload"
    session = sm.get_or_create(key)
    session.add_message("assistant", "old")
    sm.save(session)
    sm.invalidate(key)

    reloaded = sm.get_or_create(key)
    reloaded.add_message("assistant", "new")
    msg_tbl = sm._msg_table()
    with (
        patch.object(
            msg_tbl, "search", side_effect=AssertionError("reload append should not read rows")
        ),
        patch.object(
            msg_tbl,
            "count_rows",
            side_effect=AssertionError("reload append should not count rows"),
        ),
    ):
        sm.save(reloaded)

    sm.invalidate(key)
    latest = sm.get_or_create(key)
    assert [msg.get("content") for msg in latest.messages] == ["old", "new"]
