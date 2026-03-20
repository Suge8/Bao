from __future__ import annotations

from typing import cast

from tests._memory_embedding_lifecycle_fakes import _build_store, _FakeEmbed, _FakeTable


def test_backfill_embeddings_adds_missing_and_keeps_unmanaged_stale_keys():
    store = _build_store()
    embed = _FakeEmbed()
    fake_tbl = _FakeTable(
        [
            {"key": "k1", "content": "alpha", "type": "history"},
            {"key": "k2", "content": "beta", "type": "experience"},
        ]
    )
    fake_vec_tbl = _FakeTable(
        [
            {"key": "k2", "content": "beta", "type": "experience", "vector": [0.1, 0.2, 0.3]},
            {"key": "k_stale", "content": "stale", "type": "history", "vector": [0.1, 0.2, 0.3]},
        ]
    )
    setattr(store, "_embed_fn", cast(object, embed))
    setattr(store, "_tbl", fake_tbl)
    setattr(store, "_vec_tbl", cast(object, fake_vec_tbl))

    store._backfill_embeddings()

    keys = {r.get("key") for r in fake_vec_tbl.rows}
    assert keys == {"k1", "k2", "k_stale"}
    assert embed.calls == ["alpha"]


def test_backfill_embeddings_refreshes_changed_content_for_same_key():
    store = _build_store()
    embed = _FakeEmbed()
    fake_tbl = _FakeTable([{"key": "k2", "content": "beta-new", "type": "experience"}])
    fake_vec_tbl = _FakeTable(
        [
            {
                "key": "k2",
                "content": "beta-old",
                "type": "experience",
                "vector": [0.1, 0.2, 0.3],
            }
        ]
    )
    setattr(store, "_embed_fn", cast(object, embed))
    setattr(store, "_tbl", fake_tbl)
    setattr(store, "_vec_tbl", cast(object, fake_vec_tbl))

    store._backfill_embeddings()

    assert embed.calls == ["beta-new"]
    refreshed = [r for r in fake_vec_tbl.rows if r.get("key") == "k2"]
    assert len(refreshed) == 1
    assert refreshed[0]["content"] == "beta-new"
