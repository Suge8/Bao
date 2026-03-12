from __future__ import annotations

import threading

from bao.agent.memory import MEMORY_CATEGORIES, MemoryStore


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


def _build_store(rows: list[dict[str, object]] | None = None) -> MemoryStore:
    store = MemoryStore.__new__(MemoryStore)
    store._store_lock = threading.RLock()
    store._tbl = _FakeTable(rows)
    store._vec_tbl = None
    store._embed_fn = None
    return store


def test_list_memory_categories_returns_fixed_category_dtos() -> None:
    store = _build_store(
        [
            {
                "key": "long_term_project_1",
                "type": "long_term",
                "category": "project",
                "content": "Keep auth flow simple",
                "updated_at": "2026-03-12T00:00:00",
            },
            {
                "key": "long_term_project_2",
                "type": "long_term",
                "category": "project",
                "content": "Reuse session manager",
                "updated_at": "2026-03-12T00:00:00",
            },
            {
                "key": "long_term_general_1",
                "type": "long_term",
                "category": "general",
                "content": "Prefer concise replies",
                "updated_at": "2026-03-11T00:00:00",
            },
        ]
    )

    items = store.list_memory_categories()

    assert [item["category"] for item in items] == list(MEMORY_CATEGORIES)
    project = next(item for item in items if item["category"] == "project")
    personal = next(item for item in items if item["category"] == "personal")
    assert project["char_count"] > 0
    assert project["line_count"] == 2
    assert project["fact_count"] == 2
    assert personal["is_empty"] is True
    assert personal["key"] == "long_term_personal"


def test_memory_category_mutations_roundtrip_through_dtos() -> None:
    store = _build_store()

    saved = store.get_memory_category("project")
    assert saved is not None
    assert saved["is_empty"] is True

    appended = store.append_memory_category("project", "Remember the release checklist")
    assert appended is not None
    assert appended["category"] == "project"
    assert "release checklist" in appended["content"]

    store.write_long_term("Stable summary", "project")
    rewritten = store.get_memory_category("project")
    assert rewritten is not None
    assert rewritten["content"] == "Stable summary"

    cleared = store.clear_memory_category("project")
    assert cleared is not None
    assert cleared["content"] == ""
    assert cleared["is_empty"] is True


def test_write_long_term_stores_fact_rows_and_remember_dedupes() -> None:
    store = _build_store()

    store.write_long_term("Fact A\nFact B\nFact A", "project")
    rows = store._tbl.rows

    assert [row["content"] for row in rows] == ["Fact A", "Fact B"]

    store.remember("Fact B\nFact C", "project")
    detail = store.get_memory_category("project")

    assert detail is not None
    assert detail["content"] == "Fact A\nFact B\nFact C"
    assert detail["fact_count"] == 3


def test_forget_rewrites_category_with_fresh_updated_at() -> None:
    store = _build_store(
        [
            {
                "key": "long_term_project_1",
                "type": "long_term",
                "category": "project",
                "content": "Fact A",
                "updated_at": "2026-03-10T00:00:00",
            },
            {
                "key": "long_term_project_2",
                "type": "long_term",
                "category": "project",
                "content": "Fact B",
                "updated_at": "2026-03-11T00:00:00",
            },
        ]
    )

    result = store.forget("Fact B")
    detail = store.get_memory_category("project")

    assert "Removed 1 memory entries" in result
    assert detail is not None
    assert detail["content"] == "Fact A"
    assert detail["updated_at"] != "2026-03-10T00:00:00"


def test_experience_workspace_api_supports_filter_mutate_and_promote() -> None:
    store = _build_store()
    store.append_experience(
        "Fix auth cache",
        "success",
        "Use the shared session cache instead of duplicating state.",
        quality=5,
        category="coding",
        keywords="auth, cache",
        reasoning_trace="matched existing session pattern",
    )

    items = store.list_experience_items(query="auth", min_quality=4)

    assert len(items) == 1
    item = items[0]
    assert item["task"] == "Fix auth cache"
    assert item["keywords"] == "auth, cache"
    assert item["deprecated"] is False

    key = item["key"]
    assert store.set_experience_deprecated(key, True) is True
    deprecated = store.get_experience_item(key)
    assert deprecated is not None
    assert deprecated["deprecated"] is True

    promoted = store.promote_experience_to_memory(key, "project")
    assert promoted is not None
    assert "Fix auth cache" in promoted["content"]

    assert store.delete_experience(key) is True
    assert store.get_experience_item(key) is None
