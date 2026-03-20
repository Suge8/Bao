from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from bao.utils.db import ensure_table
from tests._session_manager_lazy_init_testkit import _FakeTable


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
    legacy_dir = tmp_path / "sessions"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "desktop_local.jsonl").write_text('{"role":"assistant","content":"legacy"}\n', encoding="utf-8")

    def fake_open_or_create(
        _db: object, name: str, _sample: list[dict[str, object]]
    ) -> tuple[_FakeTable, bool]:
        opened.append(name)
        return _FakeTable(name), False

    with (
        patch("bao.session.manager.get_db", return_value=object()) as get_db,
        patch("bao.session.manager.open_or_create_table", side_effect=fake_open_or_create),
    ):
        sm = SessionManager(tmp_path)
        assert sm.list_sessions() == []
        get_db.assert_called_once_with(tmp_path)
        assert opened == ["session_meta"]


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
