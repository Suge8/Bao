from __future__ import annotations

import importlib
import threading
from typing import Any, cast
from unittest.mock import patch

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


__all__ = [
    "pytest",
    "_FakeQuery",
    "_FakeTable",
    "_list_sessions_while_meta_delete_is_blocked",
    "cast",
]
