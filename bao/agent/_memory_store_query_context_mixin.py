from __future__ import annotations

import threading
import time

from loguru import logger

from bao.agent._memory_shared import (
    _QUERY_EMBED_CACHE_MAX,
    _QUERY_EMBED_CACHE_TTL_S,
    _RecallQueryContext,
)


class _MemoryStoreQueryContextMixin:
    def _ensure_query_embed_cache(self) -> None:
        if not hasattr(self, "_query_embed_cache"):
            self._query_embed_cache = {}
        if not hasattr(self, "_query_embed_cache_lock"):
            self._query_embed_cache_lock = threading.Lock()

    def _ensure_retrieval_state(self) -> None:
        if not hasattr(self, "_retrieval_revision"):
            self._retrieval_revision = 0
        if not hasattr(self, "_retrieval_index"):
            self._retrieval_index = None

    def _ensure_hit_stats_state(self) -> None:
        if not hasattr(self, "_pending_hit_updates"):
            self._pending_hit_updates = {}
        if not hasattr(self, "_hit_stats_lock"):
            self._hit_stats_lock = threading.Lock()
        if not hasattr(self, "_hit_flush_inflight"):
            self._hit_flush_inflight = False

    def _invalidate_retrieval_index(self) -> None:
        self._ensure_retrieval_state()
        self._retrieval_revision += 1
        self._retrieval_index = None

    def _compute_query_embeddings(self, query: str) -> list[list[float]]:
        embed_fn = self._embed_fn
        if not embed_fn:
            return []
        self._ensure_query_embed_cache()
        now = time.monotonic()
        with self._query_embed_cache_lock:
            cached = self._query_embed_cache.get(query)
            if cached and cached[0] > now:
                return cached[1]
            if cached:
                self._query_embed_cache.pop(query, None)

        vectors = self._call_embedding(
            lambda: embed_fn.compute_query_embeddings(query),
            op="query",
        )
        with self._query_embed_cache_lock:
            self._query_embed_cache[query] = (now + _QUERY_EMBED_CACHE_TTL_S, vectors)
            while len(self._query_embed_cache) > _QUERY_EMBED_CACHE_MAX:
                self._query_embed_cache.pop(next(iter(self._query_embed_cache)))
        return vectors

    def _build_recall_query_context(
        self,
        query: str,
        *,
        include_vectors: bool,
    ) -> _RecallQueryContext | None:
        if self.should_skip_retrieval(query):
            return None
        query_terms = tuple(self._tokenize(query))
        query_vectors: list[list[float]] | None = None
        if include_vectors and self._embed_fn and self._vec_tbl:
            try:
                query_vectors = self._compute_query_embeddings(query)
            except Exception as exc:
                logger.warning("⚠️ 查询向量失败 / query embedding failed: {}", exc)
                query_vectors = []
        return _RecallQueryContext(
            query=query,
            query_terms=query_terms,
            query_term_set=frozenset(query_terms),
            query_vectors=query_vectors,
        )
