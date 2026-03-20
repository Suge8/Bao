from __future__ import annotations

from dataclasses import dataclass

from bao.agent._sparse_text import bm25_rank_docs, tokenize_sparse_text
from bao.agent._tool_exposure_domains import TOOL_DOMAIN_CORE, build_domain_search_rows

_MAX_OPTIONAL_DOMAINS = 3
_MIN_DOMAIN_OVERLAP = 1
_SHORT_QUERY_TERM_COUNT = 2
_SECONDARY_DOMAIN_MIN_OVERLAP = 1
_SECONDARY_DOMAIN_SCORE_RATIO = 0.5


@dataclass(frozen=True, slots=True)
class DomainSelectionResult:
    selected_domains: set[str]
    scores_by_domain: dict[str, float]


def select_domains_by_bm25(
    *,
    query: str,
    enabled_domains: set[str],
) -> DomainSelectionResult:
    selected_domains = {TOOL_DOMAIN_CORE} & enabled_domains
    if not query.strip():
        return DomainSelectionResult(selected_domains=selected_domains, scores_by_domain={})
    rows = build_domain_search_rows(enabled_domains)
    query_terms = tokenize_sparse_text(query)
    doc_tokens = [tokenize_sparse_text(str(row.get("content") or "")) for row in rows]
    ranked = bm25_rank_docs(
        query=query,
        docs=rows,
        text_key="content",
        query_terms=query_terms,
        doc_tokens=doc_tokens,
    )
    scores_by_domain = {
        str(row.get("key")): score
        for score, row in ranked
        if isinstance(row.get("key"), str)
    }
    token_map = {
        str(row.get("key")): set(tokens)
        for row, tokens in zip(rows, doc_tokens, strict=False)
        if isinstance(row.get("key"), str)
    }
    query_token_set = set(query_terms)
    selected_optional = 0
    top_score = ranked[0][0] if ranked else 0.0
    for score, row in ranked:
        domain = str(row.get("key") or "")
        if not domain or domain not in enabled_domains:
            continue
        overlap = len(query_token_set & token_map.get(domain, set()))
        if overlap < _MIN_DOMAIN_OVERLAP and len(query_terms) > _SHORT_QUERY_TERM_COUNT:
            continue
        if selected_optional > 0 and (
            overlap < _SECONDARY_DOMAIN_MIN_OVERLAP
            or score < top_score * _SECONDARY_DOMAIN_SCORE_RATIO
        ):
            continue
        selected_domains.add(domain)
        selected_optional += 1
        if selected_optional >= _MAX_OPTIONAL_DOMAINS:
            break
    return DomainSelectionResult(
        selected_domains=selected_domains or ({TOOL_DOMAIN_CORE} & enabled_domains),
        scores_by_domain=scores_by_domain,
    )


__all__ = ["DomainSelectionResult", "select_domains_by_bm25"]
