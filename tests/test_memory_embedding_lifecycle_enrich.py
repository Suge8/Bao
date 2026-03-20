from __future__ import annotations

from tests._memory_embedding_lifecycle_fakes import _build_store, _FakeTable, memory_module


def test_enrich_for_rerank_filters_stale_vector_rows():
    store = _build_store()
    fake_tbl = _FakeTable(
        [
            {"key": "k1", "content": "hello", "type": "history", "quality": 3},
        ]
    )
    setattr(store, "_tbl", fake_tbl)

    vec_rows = [
        {"key": "k1", "content": "hello", "type": "history", "_distance": 0.1},
        {"key": "k_stale", "content": "gone", "type": "history", "_distance": 0.2},
    ]

    enriched = store._enrich_for_rerank(vec_rows)

    assert len(enriched) == 1
    assert enriched[0]["key"] == "k1"
    assert "_distance" in enriched[0]
    assert fake_tbl.search_calls == 2


def test_enrich_for_rerank_falls_back_for_rows_outside_index_limit(monkeypatch):
    monkeypatch.setattr(memory_module, "_BACKFILL_SCAN_LIMIT", 1)
    store = _build_store()
    fake_tbl = _FakeTable(
        [
            {"key": "k1", "content": "alpha", "type": "history", "quality": 3},
            {"key": "k2", "content": "beta", "type": "history", "quality": 5},
        ]
    )
    setattr(store, "_tbl", fake_tbl)

    enriched = store._enrich_for_rerank(
        [{"key": "k2", "content": "beta", "type": "history", "_distance": 0.1}]
    )

    assert len(enriched) == 1
    assert enriched[0]["key"] == "k2"
    assert enriched[0]["quality"] == 5
    assert fake_tbl.search_calls == 2


def test_enrich_for_rerank_uses_key_lookup_beyond_500_rows():
    store = _build_store()
    rows = [
        {"key": f"k{i}", "content": f"row-{i}", "type": "history", "quality": 3}
        for i in range(1200)
    ]
    setattr(store, "_tbl", _FakeTable(rows))

    vec_rows = [{"key": "k1100", "content": "stale", "type": "history", "_distance": 0.05}]
    enriched = store._enrich_for_rerank(vec_rows)

    assert len(enriched) == 1
    assert enriched[0]["key"] == "k1100"


def test_enrich_vector_results_uses_key_lookup_beyond_500_rows():
    store = _build_store()
    rows = [
        {
            "key": f"e{i}",
            "content": f"Task: task-{i}\nLessons: l{i}",
            "type": "experience",
            "quality": 3,
            "uses": 0,
            "successes": 0,
            "outcome": "success",
            "deprecated": False,
            "updated_at": "",
            "category": "general",
        }
        for i in range(1300)
    ]
    setattr(store, "_tbl", _FakeTable(rows))

    vec_rows = [{"key": "e1250", "content": "outdated", "type": "experience", "_distance": 0.1}]
    enriched = store._enrich_vector_results(vec_rows)

    assert len(enriched) == 1
    assert enriched[0]["key"] == "e1250"


def test_enrich_vector_results_uses_single_index_scan():
    store = _build_store()
    fake_tbl = _FakeTable(
        [
            {
                "key": "e1",
                "content": "Task: task-1\nLessons: l1",
                "type": "experience",
                "quality": 3,
                "uses": 0,
                "successes": 0,
                "outcome": "success",
                "deprecated": False,
                "updated_at": "",
                "category": "general",
            },
            {
                "key": "e2",
                "content": "Task: task-2\nLessons: l2",
                "type": "experience",
                "quality": 3,
                "uses": 0,
                "successes": 0,
                "outcome": "success",
                "deprecated": False,
                "updated_at": "",
                "category": "general",
            },
        ]
    )
    setattr(store, "_tbl", fake_tbl)

    enriched = store._enrich_vector_results(
        [
            {"key": "e1", "content": "stale-1", "type": "experience", "_distance": 0.1},
            {"key": "e2", "content": "stale-2", "type": "experience", "_distance": 0.2},
        ]
    )

    assert [row["key"] for row in enriched] == ["e1", "e2"]
    assert fake_tbl.search_calls == 1


def test_enrich_vector_results_falls_back_for_rows_outside_index_limit(monkeypatch):
    monkeypatch.setattr(memory_module, "_BACKFILL_SCAN_LIMIT", 1)
    store = _build_store()
    fake_tbl = _FakeTable(
        [
            {
                "key": "e1",
                "content": "Task: task-1\nLessons: l1",
                "type": "experience",
                "quality": 3,
                "uses": 0,
                "successes": 0,
                "outcome": "success",
                "deprecated": False,
                "updated_at": "",
                "category": "general",
            },
            {
                "key": "e2",
                "content": "Task: task-2\nLessons: l2",
                "type": "experience",
                "quality": 4,
                "uses": 1,
                "successes": 1,
                "outcome": "success",
                "deprecated": False,
                "updated_at": "",
                "category": "project",
            },
        ]
    )
    setattr(store, "_tbl", fake_tbl)

    enriched = store._enrich_vector_results(
        [{"key": "e2", "content": "stale-2", "type": "experience", "_distance": 0.2}]
    )

    assert len(enriched) == 1
    assert enriched[0]["key"] == "e2"
    assert enriched[0]["category"] == "project"
    assert fake_tbl.search_calls == 2


def test_merge_candidates_preserves_both_scores_on_duplicate():
    store = _build_store()
    vec_row = {"key": "dup", "content": "shared content", "type": "history", "_distance": 0.1}
    text_row = {"key": "dup", "content": "shared content", "type": "history", "_text_score": 2.5}

    merged = store._merge_memory_candidates([vec_row], [text_row])

    assert len(merged) == 1
    assert merged[0]["key"] == "dup"
    assert merged[0]["_distance"] == 0.1
    assert merged[0]["_text_score"] == 2.5
