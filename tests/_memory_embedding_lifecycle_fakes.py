from __future__ import annotations

import threading
from typing import Any

import bao.agent.memory as memory_module
from bao.agent.memory import MemoryStore


def _matches_where(row: dict[str, object], where: str | None) -> bool:
    if not where:
        return True
    if " AND " in where:
        return all(_matches_where(row, part.strip()) for part in where.split(" AND "))
    if where == "type != '_init_'":
        return row.get("type") != "_init_"
    if where == "type = 'experience'":
        return row.get("type") == "experience"
    if where == "type = 'long_term'":
        return row.get("type") == "long_term"
    if where.startswith("category = '") and where.endswith("'"):
        category = where[len("category = '") : -1]
        return row.get("category") == category
    if where.startswith("key = '") and where.endswith("'"):
        key = where[len("key = '") : -1]
        return row.get("key") == key
    if where.startswith("content = '") and where.endswith("'"):
        content = where[len("content = '") : -1]
        return row.get("content") == content
    if where == "type NOT IN ('experience', 'long_term')":
        return row.get("type") not in {"experience", "long_term"}
    return True


class _FakeSearch:
    def __init__(self, rows: list[dict[str, object]]):
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
        rows = [r for r in self._rows if _matches_where(r, self._where)]
        if self._limit is not None:
            rows = rows[: self._limit]
        return [dict(r) for r in rows]


class _FakeTable:
    def __init__(self, rows: list[dict[str, object]] | None = None):
        self.rows = [dict(r) for r in (rows or [])]
        self.search_calls = 0
        self.add_calls: list[list[dict[str, object]]] = []
        self.delete_calls: list[str] = []

    def search(self, *_args: Any, **_kwargs: Any):
        self.search_calls += 1
        return _FakeSearch(self.rows)

    def add(self, rows: list[dict[str, object]]):
        self.add_calls.append([dict(row) for row in rows])
        for row in rows:
            self.rows.append(dict(row))

    def delete(self, where: str):
        self.delete_calls.append(where)
        self.rows = [r for r in self.rows if not _matches_where(r, where)]


class _FakeDB:
    def __init__(self):
        self.tables: dict[str, _FakeTable] = {}

    def create_table(self, name: str, data: list[dict[str, object]]):
        tbl = _FakeTable(data)
        self.tables[name] = tbl
        return tbl

    def open_table(self, name: str):
        return self.tables[name]

    def drop_table(self, name: str):
        if name not in self.tables:
            raise KeyError(name)
        del self.tables[name]


class _FakeEmbed:
    def __init__(self):
        self.calls: list[str] = []

    def compute_source_embeddings(self, texts: list[str]):
        self.calls.extend(texts)
        return [[0.1, 0.2, 0.3] for _ in texts]


class _FlakyEmbed:
    def __init__(self):
        self.query_calls = 0

    def compute_query_embeddings(self, _query: str):
        self.query_calls += 1
        if self.query_calls == 1:
            raise TimeoutError("temporary timeout")
        return [[0.9, 0.1]]


class _QueryEmbed:
    def compute_query_embeddings(self, _query: str):
        return [[0.4, 0.6]]


class _CountingQueryEmbed:
    def __init__(self):
        self.calls = 0

    def compute_query_embeddings(self, _query: str):
        self.calls += 1
        return [[0.4, 0.6]]


class _DeferredFuture:
    def __init__(self, fn, args, kwargs):
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._callbacks = []
        self._ran = False
        self._result = None
        self._exc: Exception | None = None

    def add_done_callback(self, callback):
        self._callbacks.append(callback)

    def run(self):
        if self._ran:
            return
        self._ran = True
        try:
            self._result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:  # pragma: no cover - helper path
            self._exc = exc
        for callback in self._callbacks:
            callback(self)

    def result(self):
        if self._exc is not None:
            raise self._exc
        return self._result


class _DeferredExecutor:
    def __init__(self):
        self.futures: list[_DeferredFuture] = []

    def submit(self, fn, *args, **kwargs):
        future = _DeferredFuture(fn, args, kwargs)
        self.futures.append(future)
        return future

    def run_all(self):
        for future in list(self.futures):
            future.run()


def _build_store() -> MemoryStore:
    store = MemoryStore.__new__(MemoryStore)
    store._store_lock = threading.RLock()
    store._embed_timeout_s = 1
    store._embed_retry_attempts = 2
    store._embed_retry_backoff_ms = 0
    return store


__all__ = [
    "_build_store",
    "_CountingQueryEmbed",
    "_DeferredExecutor",
    "_FakeDB",
    "_FakeEmbed",
    "_FakeTable",
    "_FakeSearch",
    "_FlakyEmbed",
    "_QueryEmbed",
    "memory_module",
    "MemoryStore",
]
