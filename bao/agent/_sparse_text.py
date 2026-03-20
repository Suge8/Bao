from __future__ import annotations

from math import log
from typing import Any

_MIN_TOKEN_LENGTH = 2
_CJK_RANGES = (
    ("\u3400", "\u9fff"),
    ("\u3040", "\u30ff"),
    ("\uac00", "\ud7af"),
)


def is_cjk_char(char: str) -> bool:
    return any(start <= char <= end for start, end in _CJK_RANGES)


def tokenize_sparse_text(text: str) -> list[str]:
    normalized = str(text or "").lower()
    if not normalized:
        return []
    ascii_tokens = _collect_ascii_tokens(normalized)
    cjk_tokens = _collect_cjk_tokens(normalized)
    return [*ascii_tokens, *cjk_tokens]


def bm25_rank_docs(
    *,
    query: str,
    docs: list[dict[str, Any]],
    text_key: str = "content",
    k1: float = 1.2,
    b: float = 0.75,
    query_terms: list[str] | None = None,
    doc_tokens: list[list[str] | tuple[str, ...]] | None = None,
) -> list[tuple[float, dict[str, Any]]]:
    terms = list(query_terms) if query_terms is not None else tokenize_sparse_text(query)
    if not terms or not docs:
        return []
    ranked_tokens = doc_tokens or [
        tokenize_sparse_text(str(doc.get(text_key) or ""))
        for doc in docs
    ]
    avgdl = _average_doc_length(ranked_tokens)
    df = _document_frequency(terms, ranked_tokens)
    return _score_bm25_docs(
        docs=docs,
        doc_tokens=ranked_tokens,
        query_terms=terms,
        df=df,
        avgdl=avgdl,
        k1=k1,
        b=b,
    )


def _collect_ascii_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    buffer: list[str] = []
    for char in text:
        if char.isascii() and char.isalnum():
            buffer.append(char)
            continue
        _flush_ascii_buffer(tokens, buffer)
    _flush_ascii_buffer(tokens, buffer)
    return tokens


def _flush_ascii_buffer(tokens: list[str], buffer: list[str]) -> None:
    if len(buffer) >= _MIN_TOKEN_LENGTH:
        tokens.append("".join(buffer))
    buffer.clear()


def _collect_cjk_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    segment: list[str] = []
    for char in text:
        if is_cjk_char(char):
            segment.append(char)
            continue
        _flush_cjk_segment(tokens, segment)
    _flush_cjk_segment(tokens, segment)
    return tokens


def _flush_cjk_segment(tokens: list[str], segment: list[str]) -> None:
    if not segment:
        return
    for index in range(len(segment) - 1):
        tokens.append(segment[index] + segment[index + 1])
    segment.clear()


def _average_doc_length(doc_tokens: list[list[str] | tuple[str, ...]]) -> float:
    total_len = sum(len(tokens) for tokens in doc_tokens)
    return total_len / len(doc_tokens) if doc_tokens else 1.0


def _document_frequency(
    query_terms: list[str],
    doc_tokens: list[list[str] | tuple[str, ...]],
) -> dict[str, int]:
    return {
        term: sum(1 for tokens in doc_tokens if term in tokens)
        for term in query_terms
    }


def _score_bm25_docs(
    *,
    docs: list[dict[str, Any]],
    doc_tokens: list[list[str] | tuple[str, ...]],
    query_terms: list[str],
    df: dict[str, int],
    avgdl: float,
    k1: float,
    b: float,
) -> list[tuple[float, dict[str, Any]]]:
    n_docs = len(docs)
    scored: list[tuple[float, dict[str, Any]]] = []
    for index, tokens in enumerate(doc_tokens):
        if not tokens:
            continue
        tf_map: dict[str, int] = {}
        for token in tokens:
            tf_map[token] = tf_map.get(token, 0) + 1
        score = 0.0
        doc_length = len(tokens)
        for term in query_terms:
            tf = tf_map.get(term, 0)
            if tf == 0:
                continue
            matches = df.get(term, 0)
            idf = log((n_docs - matches + 0.5) / (matches + 0.5) + 1.0)
            score += idf * (tf * (k1 + 1)) / (
                tf + k1 * (1 - b + b * doc_length / avgdl)
            )
        if score > 0:
            scored.append((score, docs[index]))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


__all__ = ["bm25_rank_docs", "is_cjk_char", "tokenize_sparse_text"]
