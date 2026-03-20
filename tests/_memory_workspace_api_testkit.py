from __future__ import annotations

import threading

from bao.agent.memory import MemoryStore


def _matches_where(row: dict[str, object], where: str | None) -> bool:
    if not where:
        return True
    if " AND " in where:
        return all(_matches_where(row, part.strip()) for part in where.split(" AND "))
    if where == "type = 'long_term'":
        return row.get("type") == "long_term"
    if where == "type = 'experience'":
        return row.get("type") == "experience"
    if where.startswith("type = '") and where.endswith("'"):
        return row.get("type") == where[len("type = '") : -1]
    if where.startswith("category = '") and where.endswith("'"):
        return row.get("category") == where[len("category = '") : -1]
    if where.startswith("key = '") and where.endswith("'"):
        return row.get("key") == where[len("key = '") : -1]
    return True


class _FakeSearch:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self._where: str | None = None
        self._limit: int | None = None

    def where(self, expr: str):
        self._where = expr
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def to_list(self) -> list[dict[str, object]]:
        rows = [row for row in self._rows if _matches_where(row, self._where)]
        if self._limit is not None:
            rows = rows[: self._limit]
        return [dict(row) for row in rows]


class _FakeTable:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = [dict(row) for row in (rows or [])]

    def search(self, *_args, **_kwargs):
        return _FakeSearch(self.rows)

    def add(self, rows: list[dict[str, object]]):
        for row in rows:
            self.rows.append(dict(row))

    def delete(self, where: str):
        self.rows = [row for row in self.rows if not _matches_where(row, where)]


def build_store(rows: list[dict[str, object]] | None = None) -> MemoryStore:
    store = MemoryStore.__new__(MemoryStore)
    store._store_lock = threading.RLock()
    store._tbl = _FakeTable(rows)
    store._vec_tbl = None
    store._embed_fn = None
    return store
