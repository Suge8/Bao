from __future__ import annotations

from math import log
from typing import Any

from bao.agent._memory_experience_models import Bm25RankRequest, Bm25ScoreRequest
from bao.agent._sparse_text import bm25_rank_docs, tokenize_sparse_text


class _MemoryStoreTextSupportMixin:
    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return tokenize_sparse_text(text)

    @staticmethod
    def _normalize_low_information_query(query: str) -> str:
        return (
            query.lower()
            .replace(" ", "")
            .replace("\n", "")
            .strip(".,;:!?()[]{}\"'`~。？！；：、，…")
        )

    def should_skip_retrieval(self, query: str) -> bool:
        from bao.agent._memory_shared import _LOW_INFORMATION_QUERIES

        normalized = self._normalize_low_information_query(query)
        return not normalized or normalized in _LOW_INFORMATION_QUERIES

    @staticmethod
    def _bm25_rank(request: Bm25RankRequest) -> list[tuple[float, dict[str, Any]]]:
        return bm25_rank_docs(
            query=request.query,
            docs=request.docs,
            text_key="content",
            k1=request.k1,
            b=request.b,
            query_terms=request.query_terms,
            doc_tokens=request.doc_tokens,
        )

    @staticmethod
    def _average_doc_length(doc_tokens: list[list[str] | tuple[str, ...]]) -> float:
        total_len = sum(len(tokens) for tokens in doc_tokens)
        return total_len / len(doc_tokens) if doc_tokens else 1.0

    @staticmethod
    def _document_frequency(
        query_terms: list[str],
        doc_tokens: list[list[str] | tuple[str, ...]],
    ) -> dict[str, int]:
        return {
            term: sum(1 for tokens in doc_tokens if term in tokens)
            for term in query_terms
        }

    @staticmethod
    def _score_bm25_docs(request: Bm25ScoreRequest) -> list[tuple[float, dict[str, Any]]]:
        n_docs = len(request.docs)
        scored: list[tuple[float, dict[str, Any]]] = []
        for index, tokens in enumerate(request.doc_tokens):
            if not tokens:
                continue
            dl = len(tokens)
            tf_map: dict[str, int] = {}
            for token in tokens:
                tf_map[token] = tf_map.get(token, 0) + 1
            score = 0.0
            for term in request.query_terms:
                tf = tf_map.get(term, 0)
                if tf == 0:
                    continue
                n_qt = request.df.get(term, 0)
                idf = log((n_docs - n_qt + 0.5) / (n_qt + 0.5) + 1.0)
                score += idf * (tf * (request.k1 + 1)) / (
                    tf + request.k1 * (1 - request.b + request.b * dl / request.avgdl)
                )
            if score > 0:
                scored.append((score, request.docs[index]))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored

    def _fallback_text_search(
        self,
        query: str,
        type_filter: str | None = None,
        limit: int = 5,
        exclude_types: list[str] | None = None,
    ) -> list[str]:
        rows = self._fallback_text_candidates(
            query,
            type_filter=type_filter,
            limit=limit,
            exclude_types=exclude_types,
        )
        return [row["content"] for row in rows if row.get("content")]

    def _collect_long_term_parts(
        self,
        *,
        query_tokens: set[str] | None = None,
    ) -> list[tuple[str, str]]:
        index = self._get_retrieval_index()
        parts = list(index["long_term_parts"])
        if query_tokens is None:
            return parts
        tokens_by_category = index["long_term_tokens_by_category"]
        return [
            (category, content)
            for category, content in parts
            if query_tokens & tokens_by_category.get(category, set())
        ]

    @staticmethod
    def _format_long_term_parts(parts: list[tuple[str, str]], max_chars: int | None = None) -> str:
        if not parts:
            return ""
        header = "## Long-term Memory\n"
        if max_chars is None:
            result = "\n".join(f"[{category}] {content}" for category, content in parts)
            return f"{header}{result}"
        if max_chars <= len(header):
            return ""
        body_budget = max_chars - len(header)
        prefix_overhead = sum(len(f"[{category}] ") for category, _ in parts) + max(0, len(parts) - 1)
        usable = body_budget - prefix_overhead
        if usable <= 0:
            return ""

        total_raw = sum(len(content) for _, content in parts)
        budgeted: list[str] = []
        for category, content in parts:
            if total_raw <= usable:
                budgeted.append(f"[{category}] {content}")
                continue
            share = int(usable * len(content) / total_raw)
            if share <= 0:
                continue
            if len(content) > share:
                if share <= 1:
                    continue
                content = content[: share - 1] + "…"
            budgeted.append(f"[{category}] {content}")
        result = "\n".join(budgeted)
        return f"{header}{result}" if budgeted else ""
