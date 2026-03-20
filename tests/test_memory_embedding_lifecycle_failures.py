from __future__ import annotations

from typing import cast

import pytest

from tests._memory_embedding_lifecycle_fakes import _build_store, _FlakyEmbed


def test_query_embedding_fails_fast_on_retryable_error():
    store = _build_store()
    embed = _FlakyEmbed()
    setattr(store, "_embed_fn", cast(object, embed))

    with pytest.raises(TimeoutError):
        store._compute_query_embeddings("find this")

    assert embed.query_calls == 1
