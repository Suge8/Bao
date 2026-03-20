from __future__ import annotations

from tests._memory_embedding_lifecycle_fakes import _build_store, _FakeDB, _FakeTable


def test_migrate_schema_keeps_rows_beyond_10000_without_truncation():
    store = _build_store()
    fake_db = _FakeDB()
    fake_db.create_table("memory", [{"key": "legacy", "content": "x", "type": "history"}])
    fake_db.create_table(
        "memory_vectors",
        [{"key": "legacy", "content": "x", "type": "history", "vector": [0.1, 0.2]}],
    )
    setattr(store, "_db", fake_db)

    old_rows: list[dict[str, object]] = [
        {"key": f"h{i}", "content": f"c{i}", "type": "history", "updated_at": ""}
        for i in range(10050)
    ]
    old_tbl = _FakeTable(old_rows)

    migrated = store._migrate_schema(old_tbl)

    assert len(migrated.rows) == 10050
    migrated_keys = {r.get("key") for r in migrated.rows}
    assert "h0" in migrated_keys
    assert "h10049" in migrated_keys


def test_backfill_new_columns_keeps_rows_beyond_10000_without_truncation():
    store = _build_store()
    fake_db = _FakeDB()
    fake_db.create_table("memory", [{"key": "seed", "content": "x", "type": "history"}])
    setattr(store, "_db", fake_db)

    rows: list[dict[str, object]] = [
        {
            "key": f"k{i}",
            "content": f"c{i}",
            "type": "history",
            "category": "",
            "quality": 0,
            "uses": 0,
            "successes": 0,
            "outcome": "",
            "deprecated": False,
            "updated_at": "",
        }
        for i in range(10050)
    ]
    tbl = _FakeTable(rows)

    patched = store._backfill_new_columns(tbl)

    assert len(patched.rows) == 10050
    assert all("hit_count" in r for r in patched.rows)
    assert all("last_hit_at" in r for r in patched.rows)


def test_write_long_term_skips_embedding_schedule_when_unchanged():
    store = _build_store()
    setattr(
        store,
        "_tbl",
        _FakeTable(
            [
                {
                    "key": "long_term_general",
                    "content": "same",
                    "type": "long_term",
                    "category": "general",
                }
            ]
        ),
    )

    calls = {"count": 0}

    def _schedule() -> None:
        calls["count"] += 1

    setattr(store, "_schedule_long_term_embedding", _schedule)

    store.write_long_term("same", "general")
    assert calls["count"] == 0

    store.write_long_term("changed", "general")
    assert calls["count"] == 1


def test_write_categorized_memory_skips_embedding_when_unchanged():
    store = _build_store()
    setattr(
        store,
        "_tbl",
        _FakeTable(
            [
                {
                    "key": "long_term_general",
                    "content": "g",
                    "type": "long_term",
                    "category": "general",
                },
                {
                    "key": "long_term_preference",
                    "content": "p",
                    "type": "long_term",
                    "category": "preference",
                },
            ]
        ),
    )

    calls = {"count": 0}

    def _schedule() -> None:
        calls["count"] += 1

    setattr(store, "_schedule_long_term_embedding", _schedule)

    store.write_categorized_memory({"general": "g", "preference": "p"})
    assert calls["count"] == 0

    store.write_categorized_memory({"general": "g2", "preference": "p"})
    assert calls["count"] == 1


def test_remember_skips_aggregate_embedding_when_unchanged():
    store = _build_store()
    setattr(
        store,
        "_tbl",
        _FakeTable(
            [
                {
                    "key": "long_term_general",
                    "content": "alpha",
                    "type": "long_term",
                    "category": "general",
                }
            ]
        ),
    )

    calls = {"count": 0}

    def _aggregate() -> None:
        calls["count"] += 1

    setattr(store, "_embed_long_term_aggregate", _aggregate)

    store.remember("alpha", "general")
    assert calls["count"] == 0

    store.remember("beta", "general")
    assert calls["count"] == 1


def test_update_memory_skips_aggregate_embedding_when_unchanged():
    store = _build_store()
    setattr(
        store,
        "_tbl",
        _FakeTable(
            [
                {
                    "key": "long_term_general",
                    "content": "gamma",
                    "type": "long_term",
                    "category": "general",
                }
            ]
        ),
    )

    calls = {"count": 0}

    def _aggregate() -> None:
        calls["count"] += 1

    setattr(store, "_embed_long_term_aggregate", _aggregate)

    store.update_memory("general", "gamma")
    assert calls["count"] == 0

    store.update_memory("general", "delta")
    assert calls["count"] == 1


def test_delete_long_term_by_key_schedules_aggregate_embedding() -> None:
    store = _build_store()
    setattr(
        store,
        "_tbl",
        _FakeTable(
            [
                {
                    "key": "long_term_general_20260312_0001",
                    "content": "alpha",
                    "type": "long_term",
                    "category": "general",
                }
            ]
        ),
    )

    calls = {"count": 0}

    def _schedule() -> None:
        calls["count"] += 1

    setattr(store, "_schedule_long_term_embedding", _schedule)

    assert store.delete_long_term_by_key("long_term_general_20260312_0001") is True
    assert calls["count"] == 1
    assert store._tbl.rows == []
