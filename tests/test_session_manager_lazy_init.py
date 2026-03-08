from __future__ import annotations

import importlib
import threading
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from bao.utils.db import ensure_table

pytest = importlib.import_module("pytest")


class _FakeQuery:
    def where(self, _expr: str) -> "_FakeQuery":
        return self

    def limit(self, _count: int) -> "_FakeQuery":
        return self

    def to_list(self) -> list[dict[str, object]]:
        return []


class _FakeTable:
    def __init__(self, name: str):
        self.name = name
        self.indexes: list[str] = []

    def search(self) -> _FakeQuery:
        return _FakeQuery()

    def create_scalar_index(self, _column: str, *, replace: bool = False) -> None:
        del replace
        self.indexes.append(_column)

    def add(self, _rows: list[dict[str, object]]) -> None:
        return None

    def delete(self, _expr: str) -> None:
        return None

    def count_rows(self, *, filter: str) -> int:
        del filter
        return 0


def _list_sessions_while_meta_delete_is_blocked(
    sm: Any,
    key: str,
    writer: threading.Thread,
) -> list[dict[str, Any]]:
    meta_tbl = sm._meta_table()
    original_delete = meta_tbl.delete
    delete_entered = threading.Event()
    allow_finish = threading.Event()
    list_started = threading.Event()
    listed_sessions: list[list[dict[str, Any]]] = []

    def delayed_delete(expr: str) -> None:
        original_delete(expr)
        if expr == f"session_key = '{key}'":
            delete_entered.set()
            assert allow_finish.wait(timeout=1.0)

    with patch.object(meta_tbl, "delete", side_effect=delayed_delete):
        writer.start()
        assert delete_entered.wait(timeout=1.0)

        def _list_sessions() -> None:
            list_started.set()
            listed_sessions.append(sm.list_sessions())

        list_thread = threading.Thread(target=_list_sessions, daemon=True)
        list_thread.start()
        assert list_started.wait(timeout=1.0)
        list_thread.join(timeout=0.1)
        assert list_thread.is_alive()
        assert listed_sessions == []

        allow_finish.set()
        writer.join(timeout=1.0)
        list_thread.join(timeout=1.0)

    assert not writer.is_alive()
    assert not list_thread.is_alive()
    return listed_sessions[0]


def test_session_manager_init_is_lazy(tmp_path: Path) -> None:
    from bao.session.manager import SessionManager

    with (
        patch("bao.session.manager.get_db") as get_db,
        patch("bao.session.manager.open_or_create_table") as open_or_create_table,
    ):
        SessionManager(tmp_path)

    get_db.assert_not_called()
    open_or_create_table.assert_not_called()


def test_list_sessions_only_opens_meta_table(tmp_path: Path) -> None:
    from bao.session.manager import SessionManager

    opened: list[str] = []

    def fake_open_or_create(
        _db: object, name: str, _sample: list[dict[str, object]]
    ) -> tuple[_FakeTable, bool]:
        opened.append(name)
        return _FakeTable(name), False

    with (
        patch("bao.session.manager.get_db", return_value=object()) as get_db,
        patch("bao.session.manager.open_or_create_table", side_effect=fake_open_or_create),
        patch.object(SessionManager, "_migrate_legacy", autospec=True) as migrate,
    ):
        sm = SessionManager(tmp_path)
        assert sm.list_sessions() == []

    get_db.assert_called_once_with(tmp_path)
    assert opened == ["session_meta"]
    migrate.assert_called_once()
    assert migrate.call_args.args[0] is sm
    assert migrate.call_args.args[1] == tmp_path
    assert migrate.call_args.args[2].name == "session_meta"


def test_get_or_create_missing_session_keeps_messages_table_lazy(tmp_path: Path) -> None:
    from bao.session.manager import SessionManager

    opened: list[str] = []

    def fake_open_or_create(
        _db: object, name: str, _sample: list[dict[str, object]]
    ) -> tuple[_FakeTable, bool]:
        opened.append(name)
        return _FakeTable(name), False

    with (
        patch("bao.session.manager.get_db", return_value=object()),
        patch("bao.session.manager.open_or_create_table", side_effect=fake_open_or_create),
        patch.object(SessionManager, "_migrate_legacy", autospec=True),
    ):
        sm = SessionManager(tmp_path)
        session = sm.get_or_create("desktop:local::missing")

    assert session.key == "desktop:local::missing"
    assert opened == ["session_meta"]


def test_save_empty_session_keeps_messages_table_lazy(tmp_path: Path) -> None:
    from bao.session.manager import Session, SessionManager

    opened: list[str] = []

    def fake_open_or_create(
        _db: object, name: str, _sample: list[dict[str, object]]
    ) -> tuple[_FakeTable, bool]:
        opened.append(name)
        return _FakeTable(name), False

    with (
        patch("bao.session.manager.get_db", return_value=object()),
        patch("bao.session.manager.open_or_create_table", side_effect=fake_open_or_create),
        patch.object(SessionManager, "_migrate_legacy", autospec=True),
    ):
        sm = SessionManager(tmp_path)
        sm.save(Session("desktop:local::empty"))

    assert opened == ["session_meta", "session_display_tail"]


def test_creating_new_tables_builds_indexes_once(tmp_path: Path) -> None:
    from bao.session.manager import SessionManager

    created_tables: dict[str, _FakeTable] = {}

    def fake_open_or_create(
        _db: object, name: str, _sample: list[dict[str, object]]
    ) -> tuple[_FakeTable, bool]:
        table = _FakeTable(name)
        created_tables[name] = table
        return table, True

    with (
        patch("bao.session.manager.get_db", return_value=object()),
        patch("bao.session.manager.open_or_create_table", side_effect=fake_open_or_create),
        patch.object(SessionManager, "_migrate_legacy", autospec=True),
    ):
        sm = SessionManager(tmp_path)
        sm.list_sessions()
        sm.get_tail_messages("desktop:local::missing", 10)

    assert set(created_tables) == {"session_meta", "session_messages", "session_display_tail"}
    assert created_tables["session_meta"].indexes == ["session_key"]
    assert created_tables["session_messages"].indexes == ["session_key", "idx"]
    assert created_tables["session_display_tail"].indexes == ["session_key"]


def test_ensure_table_returns_existing_table() -> None:
    opened = _FakeTable("memory")

    class _FakeDb:
        def open_table(self, name: str) -> _FakeTable:
            assert name == "memory"
            return opened

        def create_table(self, name: str, data: object) -> _FakeTable:
            raise AssertionError(f"unexpected create_table({name}, {data})")

    assert ensure_table(cast(Any, _FakeDb()), "memory", []) is opened


def test_save_persists_tail_snapshot_for_background_read(tmp_path: Path) -> None:
    from bao.session.manager import SessionManager

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
    from bao.session.manager import SessionManager

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
    from bao.session.manager import SessionManager

    sm = SessionManager(tmp_path)
    key = "desktop:local::empty"
    session = sm.get_or_create(key)
    sm.save(session)

    sm.invalidate(key)

    assert sm.peek_tail_messages(key, 200) is None
    assert sm.get_tail_messages(key, 200) == []


def test_get_tail_messages_backfills_missing_empty_tail_row(tmp_path: Path) -> None:
    from bao.session.manager import SessionManager

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
    from bao.session.manager import SessionManager

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
    from bao.session.manager import SessionManager

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


def test_failed_save_does_not_leak_uncommitted_tail_snapshot(tmp_path: Path) -> None:
    from bao.session.manager import SessionManager

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
    from bao.session.manager import SessionManager

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
    from bao.session.manager import SessionManager

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


def test_save_fails_when_existing_baseline_cannot_be_loaded(tmp_path: Path) -> None:
    from bao.session.manager import SessionManager

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
    from bao.session.manager import SessionManager

    sm = SessionManager(tmp_path)
    key = "desktop:local::noop-save"
    events: list[tuple[str, str]] = []
    sm.add_change_listener(lambda event: events.append((event.session_key, event.kind)))

    session = sm.get_or_create(key)
    session.add_message("assistant", "hello")
    sm.save(session)
    events.clear()

    msg_tbl = sm._msg_table()
    with (
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
    from bao.session.manager import SessionManager

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
    from bao.session.manager import SessionManager

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
    from bao.session.manager import SessionManager

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
    from bao.session.manager import SessionManager

    sm = SessionManager(tmp_path)
    key = "desktop:local::delete-cache"
    session = sm.get_or_create(key)
    session.add_message("assistant", "bye")
    sm.save(session)

    assert sm.peek_tail_messages(key, 200) is not None
    assert sm.delete_session(key) is True
    assert sm.peek_tail_messages(key, 200) is None


def test_display_tail_cache_evicts_oldest_sessions(tmp_path: Path) -> None:
    from bao.session.manager import SessionManager

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
    from bao.session.manager import SessionManager

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


def test_list_sessions_waits_for_inflight_save_metadata_rewrite(tmp_path: Path) -> None:
    from bao.session.manager import SessionManager

    sm = SessionManager(tmp_path)
    key = "imessage:chat-1"
    session = sm.get_or_create(key)
    session.add_message("assistant", "before")
    sm.save(session)

    session.metadata["title"] = "updated"
    save_thread = threading.Thread(target=lambda: sm.save(session), daemon=True)

    listed_sessions = _list_sessions_while_meta_delete_is_blocked(sm, key, save_thread)

    assert [item["key"] for item in listed_sessions] == [key]
    assert listed_sessions[0]["metadata"]["title"] == "updated"


def test_list_sessions_waits_for_inflight_metadata_only_rewrite(tmp_path: Path) -> None:
    from bao.session.manager import SessionManager

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
    assert listed_sessions[0]["metadata"]["desktop_last_seen_ai_at"] == "2026-01-01T00:00:00"


def test_update_metadata_only_keyword_path_uses_same_meta_barrier(tmp_path: Path) -> None:
    from bao.session.manager import SessionManager

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
    assert listed_sessions[0]["metadata"]["desktop_last_seen_ai_at"] == "2026-01-02T00:00:00"
