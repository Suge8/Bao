from __future__ import annotations

from typing import TYPE_CHECKING

from ._memory_shared import RecallBundle, _RecallQueryContext

if TYPE_CHECKING:
    from bao.agent.memory import MemoryStore


class _RecallDomain:
    def __init__(self, host: "MemoryStore"):
        self._host = host

    def search_memory(
        self,
        query: str,
        limit: int = 5,
        *,
        query_context: _RecallQueryContext | None = None,
    ) -> list[str]:
        query_ctx = query_context or self._host._build_recall_query_context(query, include_vectors=True)
        if query_ctx is None:
            return []
        fetch = max(limit * 3, 6)
        vec_enriched: list[dict[str, object]] = []
        if self._host._embed_fn and self._host._vec_tbl and query_ctx.query_vectors:
            try:
                vec = query_ctx.query_vectors[0] if query_ctx.query_vectors else None
                if vec:
                    with self._host._store_lock:
                        vec_rows = self._host._vec_tbl.search(vec).where("type NOT IN ('experience', 'long_term')").limit(fetch).to_list()
                    if vec_rows:
                        vec_enriched = self._host._enrich_for_rerank(vec_rows)
            except Exception as exc:
                from loguru import logger

                logger.warning("⚠️ 语义检索失败 / semantic search failed: {}", exc)
        text_candidates = self._host._fallback_text_candidates(query_ctx.query, limit=fetch, exclude_types=["experience", "long_term"], query_terms=query_ctx.query_terms)
        candidates = self._host._merge_memory_candidates(vec_enriched, text_candidates)
        if candidates:
            reranked = self._host._rerank_candidates(candidates, limit=limit, has_vector_score=bool(vec_enriched))
            if reranked:
                return [row["content"] for row in reranked if row.get("content")]
        return []

    def recall(
        self,
        query: str,
        *,
        related_limit: int = 5,
        experience_limit: int = 3,
        long_term_chars: int | None = None,
        include_long_term: bool = True,
    ) -> RecallBundle:
        query_ctx = self._host._build_recall_query_context(query, include_vectors=True)
        if query_ctx is None:
            return RecallBundle()
        related_memory = tuple(
            self.search_memory(
                query,
                limit=related_limit,
                query_context=query_ctx,
            )
        )
        related_experience = tuple(
            self._host._experience().search_experience(
                query,
                limit=experience_limit,
                query_context=query_ctx,
            )
        )
        return RecallBundle(
            long_term_context=(
                self._host.get_relevant_memory_context(
                    query,
                    max_chars=long_term_chars,
                    query_context=query_ctx,
                )
                if include_long_term
                else ""
            ),
            related_memory=related_memory,
            related_experience=related_experience,
        )
