from __future__ import annotations

from datetime import datetime
from math import exp
from typing import TYPE_CHECKING, Any

from loguru import logger

from ._memory_experience_models import ExperienceAppendRequest, ExperienceListRequest
from ._memory_experience_query import filter_experience_items, sort_experience_items
from ._memory_shared import _RETENTION_DAYS, MEMORY_CATEGORIES

if TYPE_CHECKING:
    from bao.agent.memory import MemoryStore


class _ExperienceMemoryDomain:
    def __init__(self, host: "MemoryStore"):
        self._host = host

    def append_experience(self, request: ExperienceAppendRequest) -> None:
        row_key, content = self._persist_experience_row(request)
        self._host._embed_and_store(key=row_key, content=content, type_="experience")
        self._host._emit_change(
            scope="experience",
            operation="append",
            category=request.category,
            key=row_key,
        )

    def _persist_experience_row(
        self,
        request: ExperienceAppendRequest,
    ) -> tuple[str, str]:
        with self._host._store_lock:
            ts = datetime.now().isoformat()
            row_key = f"experience_{ts}"
            parts = [f"Task: {request.task}", f"Lessons: {request.lessons}"]
            if request.keywords:
                parts.append(f"Keywords: {request.keywords}")
            if request.reasoning_trace:
                parts.append(f"Trace: {request.reasoning_trace}")
            content = "\n".join(parts)
            self._host._tbl.add(
                [
                    self._host._make_row(
                        key=row_key,
                        content=content,
                        type_="experience",
                        category=request.category,
                        quality=request.quality,
                        outcome=request.outcome,
                        updated_at=ts,
                    )
                ]
            )
            self._host._invalidate_retrieval_index()
        return row_key, content

    def search_experience(
        self,
        query: str,
        limit: int = 3,
        *,
        query_context: Any | None = None,
    ) -> list[str]:
        query_ctx = query_context or self._host._build_recall_query_context(query, include_vectors=True)
        if query_ctx is None:
            return []
        candidates = self._host._fetch_experience_candidates(query_ctx, limit * 5)
        now = datetime.now()
        positive: list[tuple[float, dict[str, Any], str, str, str]] = []
        warnings: list[tuple[float, dict[str, Any], str, str]] = []
        for row in candidates:
            if "quality" not in row and "outcome" not in row and "updated_at" not in row:
                continue
            if row.get("deprecated"):
                continue
            quality = row.get("quality", 3)
            days_old = self._host._days_since(row.get("updated_at", ""), now)
            decay = exp(-days_old / _RETENTION_DAYS.get(quality, 90))
            conf = self._host._confidence(row)
            score = quality * decay * conf
            content = row.get("content") or ""
            outcome = row.get("outcome", "")
            if outcome == "failed":
                warnings.append((score, row, content, row.get("category") or "general"))
            else:
                positive.append((score, row, content, row.get("category") or "general", outcome or "success"))
        positive.sort(key=lambda item: item[0], reverse=True)
        warnings.sort(key=lambda item: item[0], reverse=True)
        results: list[str] = []
        hit_rows: list[dict[str, Any]] = []
        seen_categories: dict[str, str] = {}
        for _, row, content, category, outcome_str in positive:
            if len(results) >= limit - 1:
                break
            previous = seen_categories.get(category)
            if previous and previous != outcome_str:
                content = f"\u26a1 CONFLICTING experience (category '{category}'):\n{content}"
            seen_categories.setdefault(category, outcome_str)
            results.append(content)
            hit_rows.append(row)
        if warnings:
            results.append(f"\u26a0\ufe0f WARNING from past failure:\n{warnings[0][2]}")
            hit_rows.append(warnings[0][1])
        final = results[:limit]
        if hit_rows:
            self._host._schedule_hit_stats_update(hit_rows)
        return final

    def list_experience_items(self, request: ExperienceListRequest) -> list[dict[str, Any]]:
        with self._host._store_lock:
            try:
                rows = (
                    self._host._tbl.search()
                    .where("type = 'experience'")
                    .limit(max(request.limit * 2, 200))
                    .to_list()
                )
            except Exception:
                return []
        items = [self._host._experience_row_to_item(row) for row in rows]
        filtered = filter_experience_items(self._host, items, request)
        sort_experience_items(filtered, request.sort_by)
        return filtered[: request.limit]

    def get_experience_item(self, key: str) -> dict[str, Any] | None:
        if not key:
            return None
        key_safe = key.replace("'", "''")
        with self._host._store_lock:
            try:
                rows = self._host._tbl.search().where(f"type = 'experience' AND key = '{key_safe}'").limit(1).to_list()
            except Exception:
                return None
        return self._host._experience_row_to_item(rows[0]) if rows else None

    def set_experience_deprecated(self, key: str, deprecated: bool) -> bool:
        item = self.get_experience_item(key)
        if item is None:
            return False
        key_safe = key.replace("'", "''")
        with self._host._store_lock:
            try:
                rows = self._host._tbl.search().where(f"type = 'experience' AND key = '{key_safe}'").limit(1).to_list()
                if not rows:
                    return False
                self._host._update_experience(rows[0], deprecated=deprecated)
                self._host._emit_change(scope="experience", operation="deprecate" if deprecated else "restore", category=str(rows[0].get("category") or ""), key=key)
                return True
            except Exception as exc:
                logger.warning("⚠️ 更新经验停用状态失败 / set deprecated failed: {}", exc)
                return False

    def delete_experience(self, key: str) -> bool:
        if not key:
            return False
        key_safe = key.replace("'", "''")
        with self._host._store_lock:
            try:
                rows = self._host._tbl.search().where(f"type = 'experience' AND key = '{key_safe}'").limit(1).to_list()
                if not rows:
                    return False
                self._host._tbl.delete(f"type = 'experience' AND key = '{key_safe}'")
                self._host._invalidate_retrieval_index()
                self._host._delete_vector_by_key(key)
                self._host._emit_change(scope="experience", operation="delete", key=key)
                return True
            except Exception as exc:
                logger.warning("⚠️ 删除经验失败 / delete experience failed: {}", exc)
                return False

    def promote_experience_to_memory(self, key: str, category: str = "project") -> dict[str, Any] | None:
        item = self.get_experience_item(key)
        if item is None or category not in MEMORY_CATEGORIES:
            return None
        task = str(item.get("task", "")).strip()
        lessons = str(item.get("lessons", "")).strip()
        keywords = str(item.get("keywords", "")).strip()
        if not (task or lessons):
            return None
        line = f"{task} — {lessons}" if task and lessons else (task or lessons)
        if keywords:
            line = f"{line} [{keywords}]"
        self._host._ensure_domains()
        detail = self._host._long_term_domain.append_memory_category(category, line)
        self._host._emit_change(scope="experience", operation="promote", category=category, key=key)
        return detail

    def deprecate_similar(self, task_desc: str) -> int:
        return self._host._mutate_experiences(task_desc, threshold=0.5, mutator=lambda _row: {"deprecated": True}, action="🧹 标记过时 / experiences deprecated")

    def boost_experience(self, task_desc: str, delta: int = 1) -> int:
        def _mutator(row: dict[str, Any]) -> dict[str, Any] | None:
            old_quality = row.get("quality", 3)
            new_quality = max(1, min(5, old_quality + delta))
            return None if new_quality == old_quality else {"quality": new_quality}

        return self._host._mutate_experiences(task_desc, threshold=0.4, mutator=_mutator, action=f"🧠 提升经验 / experience boosted ({delta:+d})")

    def record_reuse(self, task_desc: str, success: bool) -> int:
        def _mutator(row: dict[str, Any]) -> dict[str, Any] | None:
            new_uses = row.get("uses", 0) + 1
            new_successes = row.get("successes", 0) + (1 if success else 0)
            updates: dict[str, Any] = {"uses": new_uses, "successes": new_successes}
            if new_uses >= 3:
                confidence = new_successes / new_uses
                current_quality = row.get("quality", 3)
                if confidence >= 0.8:
                    updates["quality"] = min(5, current_quality + 1)
                elif confidence < 0.4:
                    updates["quality"] = max(1, current_quality - 1)
            return updates

        sign = "+" if success else "-"
        return self._host._mutate_experiences(task_desc, threshold=0.4, mutator=_mutator, action=f"📝 记录复用 / reuse recorded ({sign})")

    def cleanup_stale(self, max_deprecated_days: int = 30, max_low_quality_days: int = 90) -> int:
        with self._host._store_lock:
            try:
                rows = self._host._tbl.search().where("type = 'experience'").limit(500).to_list()
                now = datetime.now()
                removed = 0
                for row in rows:
                    days_old = self._host._days_since(row.get("updated_at", ""), now)
                    is_deprecated = row.get("deprecated", False)
                    quality = row.get("quality", 3)
                    uses = row.get("uses", 0)
                    hit_count = row.get("hit_count", 0)
                    has_hit_tracking = bool(row.get("last_hit_at"))
                    if quality >= 5 and uses >= 3 and not is_deprecated:
                        continue
                    should_remove = (
                        (is_deprecated and days_old > max_deprecated_days)
                        or (quality <= 1 and days_old > max_low_quality_days)
                        or (has_hit_tracking and hit_count == 0 and days_old > 60 and quality <= 2)
                        or (has_hit_tracking and hit_count <= 1 and days_old > 120 and quality <= 3)
                    )
                    if should_remove and (key := row.get("key")):
                        self._host._tbl.delete(f"key = '{key}'")
                        self._host._delete_vector_by_key(key)
                        removed += 1
                if removed:
                    self._host._invalidate_retrieval_index()
                    logger.info("🧹 清理经验 / stale experiences cleaned: {}", removed)
                return removed
            except Exception as exc:
                logger.warning("⚠️ 清理经验失败 / cleanup failed: {}", exc)
                return 0
