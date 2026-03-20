from __future__ import annotations

from datetime import datetime
from math import exp
from typing import Any

from loguru import logger

from bao.agent._memory_experience_models import Bm25RankRequest
from bao.agent._memory_shared import _CATEGORY_WEIGHTS


class _MemoryStoreSearchSupportMixin:
    def _update_hit_stats(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        now = datetime.now().isoformat()
        with self._store_lock:
            try:
                row_by_key = self._lookup_hit_stat_rows(rows)
                plans = self._plan_hit_updates(row_by_key, rows, now)
                updated_count = self._apply_hit_update_batch(plans)
                if updated_count:
                    logger.debug("memory hit stats updated for {} rows", updated_count)
            except Exception as exc:
                logger.debug("hit_stats batch update skipped: {}", exc)

    def _lookup_hit_stat_rows(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        row_by_key = dict(self._get_retrieval_index()["row_by_key"])
        missing_keys = [
            key for key in (str(row.get("key") or "") for row in rows) if key and key not in row_by_key
        ]
        if missing_keys:
            row_by_key.update(self._lookup_rows_by_keys(missing_keys))
        return row_by_key

    @staticmethod
    def _coalesce_hit_updates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = str(row.get("key") or "")
            hit_delta = int(row.get("_hit_delta", 1) or 1)
            if not key or hit_delta <= 0:
                continue
            previous_delta = int((merged.get(key, {}) or {}).get("_hit_delta", 0) or 0)
            combined = dict(merged.get(key, {}))
            combined.update(dict(row))
            combined["key"] = key
            combined["_hit_delta"] = previous_delta + hit_delta
            merged[key] = combined
        return list(merged.values())

    def _plan_hit_updates(
        self,
        row_by_key: dict[str, dict[str, Any]],
        rows: list[dict[str, Any]],
        now: str,
    ) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
        plans: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for row in self._coalesce_hit_updates(rows):
            key = str(row.get("key") or "")
            hit_delta = int(row.get("_hit_delta", 1) or 1)
            current = row_by_key.get(key)
            if not key or hit_delta <= 0 or not current:
                continue
            next_row = self._make_row(
                key=key,
                content=current.get("content", ""),
                type_=current.get("type", ""),
                category=current.get("category", ""),
                quality=current.get("quality", 0),
                uses=current.get("uses", 0),
                successes=current.get("successes", 0),
                outcome=current.get("outcome", ""),
                deprecated=current.get("deprecated", False),
                updated_at=current.get("updated_at", now),
                last_hit_at=now,
                hit_count=int(current.get("hit_count", 0) or 0) + hit_delta,
            )
            plans.append((key, dict(current), next_row))
            row_by_key[key] = next_row
        return plans

    def _apply_hit_update_batch(
        self,
        plans: list[tuple[str, dict[str, Any], dict[str, Any]]],
    ) -> int:
        if not plans:
            return 0
        deleted_plans: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        try:
            for plan in plans:
                key, _, _ = plan
                key_safe = key.replace("'", "''")
                self._tbl.delete(f"key = '{key_safe}'")
                deleted_plans.append(plan)
            self._tbl.add([next_row for _, _, next_row in deleted_plans])
        except Exception:
            self._restore_hit_update_rows(deleted_plans)
            return 0
        for _, _, next_row in deleted_plans:
            self._patch_cached_retrieval_row(next_row)
        return len(deleted_plans)

    def _restore_hit_update_rows(
        self,
        plans: list[tuple[str, dict[str, Any], dict[str, Any]]],
    ) -> None:
        if not plans:
            return
        try:
            self._tbl.add([self._restore_hit_update_row(key, current) for key, current, _ in plans])
        except Exception:
            for key, _, _ in plans:
                logger.warning("⚠️ hit_stats: failed to restore row key={}", key)

    def _restore_hit_update_row(self, key: str, current: dict[str, Any]) -> dict[str, Any]:
        return self._make_row(
            key=key,
            content=current.get("content", ""),
            type_=current.get("type", ""),
            **{
                name: current.get(name, default)
                for name, default in {
                    "category": "",
                    "quality": 0,
                    "uses": 0,
                    "successes": 0,
                    "outcome": "",
                    "deprecated": False,
                    "updated_at": "",
                    "last_hit_at": "",
                    "hit_count": 0,
                }.items()
            },
        )

    def _rerank_candidates(
        self,
        candidates: list[dict[str, Any]],
        *,
        limit: int,
        has_vector_score: bool = False,
    ) -> list[dict[str, Any]]:
        now = datetime.now()
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in candidates:
            if row.get("deprecated"):
                continue
            if has_vector_score and "_distance" in row:
                semantic = max(0.0, 1.0 - row["_distance"] / 2.0)
            else:
                semantic = 0.5

            text_score_raw = row.get("_text_score", 0.0)
            text_signal = (
                float(text_score_raw) / (1.0 + float(text_score_raw))
                if isinstance(text_score_raw, (int, float)) and text_score_raw > 0
                else 0.0
            )
            days_old = self._days_since(row.get("updated_at", ""), now)
            recency = exp(-days_old / 90)
            category = row.get("category") or "general"
            category_weight = _CATEGORY_WEIGHTS.get(category, 0.4)
            quality = row.get("quality", 3) / 5.0
            importance = 0.5 * category_weight + 0.5 * quality
            reliability = self._confidence(row)
            score = (
                0.30 * semantic
                + 0.20 * text_signal
                + 0.20 * recency
                + 0.20 * importance
                + 0.10 * reliability
            )
            scored.append((score, row))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in scored[:limit]]

    def _enrich_for_rerank(self, vec_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            return self._enrich_vector_rows(
                vec_rows,
                content_map_key="row_by_content_type",
                content_lookup_uses_type=True,
            )
        except Exception:
            return vec_rows

    @staticmethod
    def _candidate_identity(row: dict[str, Any]) -> tuple[str, ...]:
        key = str(row.get("key", "")).strip()
        if key:
            return ("key", key)
        return ("content", str(row.get("type", "")), str(row.get("content", "")))

    def _merge_memory_candidates(self, *groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: dict[tuple[str, ...], dict[str, Any]] = {}
        for group in groups:
            for row in group:
                identity = self._candidate_identity(row)
                if identity in seen:
                    existing = seen[identity]
                    if "_text_score" in row and "_text_score" not in existing:
                        existing["_text_score"] = row["_text_score"]
                    if "_distance" in row and "_distance" not in existing:
                        existing["_distance"] = row["_distance"]
                    continue
                seen[identity] = row
                merged.append(row)
        return merged

    def _fallback_text_candidates(
        self,
        query: str,
        type_filter: str | None = None,
        limit: int = 5,
        exclude_types: list[str] | None = None,
        query_terms: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            index = self._get_retrieval_index()
            rows = self._retrieval_rows(
                index,
                type_filter=type_filter,
                exclude_types=exclude_types,
                limit=100,
            )
            if not rows:
                return []
            ranked_terms = list(query_terms) if query_terms is not None else self._tokenize(query)
            ranked = self._bm25_rank(
                Bm25RankRequest(
                    query=query,
                    docs=rows,
                    query_terms=ranked_terms,
                    doc_tokens=[self._row_tokens_from_index(row, index) for row in rows],
                )
            )
            if ranked:
                out: list[dict[str, Any]] = []
                for score, row in ranked[:limit]:
                    if not row.get("content"):
                        continue
                    item = dict(row)
                    item["_text_score"] = score
                    out.append(item)
                return out
            return [dict(row) for row in rows[:limit] if row.get("content")]
        except Exception as exc:
            logger.warning("⚠️ 文本回退失败 / text fallback failed: {}", exc)
            return []

    def _fetch_experience_candidates(
        self,
        query_context,
        fetch: int,
    ) -> list[dict[str, Any]]:
        if self._embed_fn and self._vec_tbl and query_context.query_vectors:
            try:
                vec = query_context.query_vectors[0] if query_context.query_vectors else None
                if not vec:
                    raise ValueError("query embedding returned empty vector")
                with self._store_lock:
                    vec_rows = (
                        self._vec_tbl.search(vec).where("type = 'experience'").limit(fetch).to_list()
                    )
                if vec_rows and (enriched := self._enrich_vector_results(vec_rows)):
                    return enriched
            except Exception as exc:
                logger.warning("⚠️ 经验检索失败 / experience search failed: {}", exc)
        try:
            return self._fallback_text_candidates(
                query_context.query,
                type_filter="experience",
                limit=fetch,
                query_terms=query_context.query_terms,
            )
        except Exception as exc:
            logger.warning("⚠️ 回退检索失败 / fallback search failed: {}", exc)
            return []

    def _enrich_vector_results(self, vec_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            return self._enrich_vector_rows(
                vec_rows,
                content_map_key="experience_by_content",
                type_filter="experience",
            )
        except Exception:
            return []

    def _enrich_vector_rows(
        self,
        vec_rows: list[dict[str, Any]],
        *,
        content_map_key: str,
        type_filter: str | None = None,
        content_lookup_uses_type: bool = False,
    ) -> list[dict[str, Any]]:
        index = self._get_retrieval_index()
        key_map, content_map = self._resolve_index_rows(
            index,
            vec_rows=vec_rows,
            content_map_key=content_map_key,
            type_filter=type_filter,
        )
        enriched: list[dict[str, Any]] = []
        for vec_row in vec_rows:
            key = str(vec_row.get("key", "") or "")
            content = str(vec_row.get("content", "") or "")
            type_ = str(vec_row.get("type", "") or "")
            content_lookup_key: Any = (content, type_) if content_lookup_uses_type else content
            matched = key_map.get(key) if key else content_map.get(content_lookup_key)
            if matched is None and not key:
                matched = self._lookup_row_by_content_type(content, type_filter or type_)
                if matched is not None:
                    content_map[content_lookup_key] = matched
            if not matched:
                continue
            merged = dict(matched)
            if "_distance" in vec_row:
                merged["_distance"] = vec_row["_distance"]
            enriched.append(merged)
        return enriched
