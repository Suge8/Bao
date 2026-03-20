from __future__ import annotations

from typing import cast

from tests._memory_embedding_lifecycle_fakes import (
    _build_store,
    _CountingQueryEmbed,
    _FakeTable,
    _QueryEmbed,
)


def test_search_memory_merges_vector_and_text_candidates():
    store = _build_store()
    setattr(store, "_embed_fn", cast(object, _QueryEmbed()))
    setattr(
        store,
        "_tbl",
        _FakeTable(
            [
                {
                    "key": "k_vec",
                    "content": "vector memory content",
                    "type": "history",
                    "category": "general",
                    "quality": 3,
                    "uses": 0,
                    "successes": 0,
                    "updated_at": "",
                    "deprecated": False,
                },
                {
                    "key": "k_text",
                    "content": "special token memory",
                    "type": "history",
                    "category": "general",
                    "quality": 3,
                    "uses": 0,
                    "successes": 0,
                    "updated_at": "",
                    "deprecated": False,
                },
            ]
        ),
    )
    setattr(
        store,
        "_vec_tbl",
        cast(
            object,
            _FakeTable(
                [
                    {
                        "key": "k_vec",
                        "content": "vector memory content",
                        "type": "history",
                        "_distance": 0.05,
                    }
                ]
            ),
        ),
    )

    results = store.search_memory("special token", limit=2)

    assert "vector memory content" in results
    assert "special token memory" in results


def _seed_recall_tables(store, embed) -> None:
    setattr(store, "_embed_fn", cast(object, embed))
    setattr(
        store,
        "_tbl",
        _FakeTable(
            [
                {
                    "key": "k_vec",
                    "content": "special token memory",
                    "type": "history",
                    "category": "general",
                    "quality": 3,
                    "uses": 0,
                    "successes": 0,
                    "updated_at": "",
                    "deprecated": False,
                },
                {
                    "key": "e_vec",
                    "content": "Task: special token task\nLessons: remembered lesson",
                    "type": "experience",
                    "category": "project",
                    "quality": 4,
                    "uses": 1,
                    "successes": 1,
                    "outcome": "success",
                    "updated_at": "",
                    "deprecated": False,
                },
            ]
        ),
    )
    setattr(
        store,
        "_vec_tbl",
        cast(
            object,
            _FakeTable(
                [
                    {
                        "key": "k_vec",
                        "content": "special token memory",
                        "type": "history",
                        "_distance": 0.05,
                    },
                    {
                        "key": "e_vec",
                        "content": "Task: special token task\nLessons: remembered lesson",
                        "type": "experience",
                        "_distance": 0.08,
                    },
                ]
            ),
        ),
    )


def test_recall_reuses_query_context_for_memory_and_experience():
    store = _build_store()
    embed = _CountingQueryEmbed()
    _seed_recall_tables(store, embed)

    bundle = store.recall("special token", related_limit=1, experience_limit=2)

    assert embed.calls == 1
    assert bundle.related_memory == ("special token memory",)
    assert len(bundle.related_experience) == 1
