from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from bao.utils.db import ensure_table


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

    assert opened == ["session_meta"]


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

    assert set(created_tables) == {"session_meta", "session_messages"}
    assert created_tables["session_meta"].indexes == ["session_key"]
    assert created_tables["session_messages"].indexes == ["session_key", "idx"]


def test_ensure_table_returns_existing_table() -> None:
    opened = _FakeTable("memory")

    class _FakeDb:
        def open_table(self, name: str) -> _FakeTable:
            assert name == "memory"
            return opened

        def create_table(self, name: str, data: object) -> _FakeTable:
            raise AssertionError(f"unexpected create_table({name}, {data})")

    assert ensure_table(cast(Any, _FakeDb()), "memory", []) is opened
