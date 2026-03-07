from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import importlib
import threading

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
