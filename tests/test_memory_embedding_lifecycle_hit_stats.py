from __future__ import annotations

import time

from bao.agent.memory import MemoryStore
from tests._memory_embedding_lifecycle_fakes import (
    _build_store,
    _DeferredExecutor,
    _FakeTable,
    memory_module,
)


def test_schedule_hit_stats_update_coalesces_same_key_before_flush(monkeypatch):
    store = _build_store()
    fake_tbl = _FakeTable(
        [
            {
                "key": "k1",
                "content": "alpha",
                "type": "history",
                "updated_at": "2026-03-14T00:00:00",
                "hit_count": 1,
                "last_hit_at": "",
            },
            {
                "key": "k2",
                "content": "beta",
                "type": "history",
                "updated_at": "2026-03-14T00:00:00",
                "hit_count": 0,
                "last_hit_at": "",
            },
        ]
    )
    executor = _DeferredExecutor()
    monkeypatch.setattr(MemoryStore, "_MEMORY_BG_EXECUTOR", executor)
    setattr(store, "_tbl", fake_tbl)

    store._schedule_hit_stats_update(
        [
            {"key": "k1", "content": "alpha", "type": "history", "hit_count": 1},
            {"key": "k1", "content": "alpha", "type": "history", "hit_count": 1},
        ]
    )
    store._schedule_hit_stats_update(
        [
            {"key": "k2", "content": "beta", "type": "history", "hit_count": 0},
            {"key": "k1", "content": "alpha", "type": "history", "hit_count": 1},
        ]
    )

    assert len(executor.futures) == 1
    assert store._pending_hit_updates["k1"]["_hit_delta"] == 3
    assert store._pending_hit_updates["k2"]["_hit_delta"] == 1

    executor.run_all()

    rows_by_key = {str(row["key"]): row for row in fake_tbl.rows}
    assert rows_by_key["k1"]["hit_count"] == 4
    assert rows_by_key["k2"]["hit_count"] == 1
    assert fake_tbl.delete_calls.count("key = 'k1'") == 1
    assert fake_tbl.delete_calls.count("key = 'k2'") == 1


def test_update_hit_stats_falls_back_for_rows_outside_index_limit(monkeypatch):
    monkeypatch.setattr(memory_module, "_BACKFILL_SCAN_LIMIT", 1)
    store = _build_store()
    fake_tbl = _FakeTable(
        [
            {
                "key": "k1",
                "content": "alpha",
                "type": "history",
                "updated_at": "2026-03-14T00:00:00",
                "hit_count": 1,
                "last_hit_at": "",
            },
            {
                "key": "k2",
                "content": "beta",
                "type": "history",
                "updated_at": "2026-03-14T00:00:00",
                "hit_count": 2,
                "last_hit_at": "",
            },
        ]
    )
    setattr(store, "_tbl", fake_tbl)

    store._update_hit_stats([{"key": "k2", "_hit_delta": 3}])

    rows_by_key = {str(row["key"]): row for row in fake_tbl.rows}
    assert rows_by_key["k2"]["hit_count"] == 5
    assert fake_tbl.delete_calls.count("key = 'k2'") == 1


def test_update_hit_stats_patches_cached_retrieval_index_without_rebuild():
    store = _build_store()
    fake_tbl = _FakeTable(
        [
            {
                "key": "k1",
                "content": "alpha",
                "type": "history",
                "updated_at": "2026-03-14T00:00:00",
                "hit_count": 1,
                "last_hit_at": "",
            }
        ]
    )
    setattr(store, "_tbl", fake_tbl)

    first_index = store._get_retrieval_index()
    store._update_hit_stats([{"key": "k1", "_hit_delta": 2}])
    second_index = store._get_retrieval_index()

    assert second_index is first_index
    assert second_index["row_by_key"]["k1"]["hit_count"] == 3
    assert fake_tbl.search_calls == 1


def test_run_with_timeout_uses_executor_timeout_path():
    started = time.time()

    def _slow() -> str:
        time.sleep(0.05)
        return "done"

    try:
        MemoryStore._run_with_timeout(0, _slow)
        assert False
    except TimeoutError as exc:
        assert "timed out" in str(exc)
        assert MemoryStore._is_transient_embedding_error(exc)
    assert time.time() - started < 0.05
