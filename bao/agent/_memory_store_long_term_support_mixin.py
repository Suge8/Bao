from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger


class _MemoryStoreLongTermSupportMixin:
    def _make_row(self, *, key: str, content: str, type_: str, **extra) -> dict[str, Any]:
        row = {
            "key": key,
            "content": content,
            "type": type_,
            "category": "",
            "quality": 0,
            "uses": 0,
            "successes": 0,
            "outcome": "",
            "deprecated": False,
            "updated_at": extra.pop("updated_at", datetime.now().isoformat()),
            "last_hit_at": extra.pop("last_hit_at", ""),
            "hit_count": extra.pop("hit_count", 0),
        }
        row.update(extra)
        return row

    @staticmethod
    def _normalize_memory_facts(content: Any, *, max_chars: int) -> list[str]:
        if max_chars <= 0:
            return []
        raw_lines = [str(item) for item in content] if isinstance(content, list) else str(content).splitlines()
        facts: list[str] = []
        seen: set[str] = set()
        used = 0
        for raw in raw_lines:
            fact = raw.strip()
            if not fact or fact in seen:
                continue
            prefix = 1 if facts else 0
            remaining = max_chars - used - prefix
            if remaining <= 0:
                break
            if len(fact) > remaining:
                if remaining <= 1:
                    break
                fact = fact[: remaining - 1].rstrip() + "…"
            if not fact or fact in seen:
                continue
            seen.add(fact)
            facts.append(fact)
            used += len(fact) + prefix
        return facts

    @staticmethod
    def _join_memory_facts(facts: list[str]) -> str:
        return "\n".join(facts)

    @staticmethod
    def _is_legacy_long_term_key(key: str, category: str) -> bool:
        normalized = key.strip()
        return normalized in {"", "long_term", f"long_term_{category}"}

    @staticmethod
    def _long_term_fact_key(category: str, updated_at: str, index: int) -> str:
        stamp = (updated_at or datetime.now().isoformat()).replace(":", "").replace("-", "")
        stamp = stamp.replace(".", "").replace("+", "").replace("T", "_")[:24]
        return f"long_term_{category}_{stamp}_{index:04d}"

    def _migrate_long_term_facts(self) -> None:
        with self._store_lock:
            try:
                rows = self._tbl.search().where("type = 'long_term'").limit(200).to_list()
            except Exception as exc:
                logger.debug("long-term fact migration skipped: {}", exc)
                return

            changed = False
            for row in rows:
                category = str(row.get("category") or "general")
                key = str(row.get("key") or "")
                if not self._is_legacy_long_term_key(key, category):
                    continue
                updated_at = str(row.get("updated_at") or datetime.now().isoformat())
                facts = self._normalize_memory_facts(
                    row.get("content", ""),
                    max_chars=self._memory_cap(category),
                )
                key_safe = key.replace("'", "''")
                self._tbl.delete(f"type = 'long_term' AND key = '{key_safe}'")
                changed = True
                if not facts:
                    continue
                self._tbl.add(
                    [
                        self._make_row(
                            key=self._long_term_fact_key(category, updated_at, idx),
                            content=fact,
                            type_="long_term",
                            category=category,
                            updated_at=updated_at,
                        )
                        for idx, fact in enumerate(facts, start=1)
                    ]
                )
            if changed:
                self._invalidate_retrieval_index()
                logger.info("🔀 长期记忆事实化 / migrated long-term memory to fact rows")

    def _read_long_term_rows_locked(self) -> list[dict[str, Any]]:
        rows = self._tbl.search().where("type = 'long_term'").limit(200).to_list()
        rows.sort(
            key=lambda row: (
                str(row.get("category") or "general"),
                str(row.get("updated_at", "")),
                str(row.get("key", "")),
            )
        )
        return rows

    def _read_long_term_fact_rows_locked(self, category: str) -> list[dict[str, Any]]:
        return [
            row
            for row in self._read_long_term_rows_locked()
            if str(row.get("category") or "general") == category and str(row.get("content", "")).strip()
        ]

    def _read_long_term_facts_locked(self, category: str) -> list[str]:
        return [
            str(row.get("content", "")).strip()
            for row in self._read_long_term_fact_rows_locked(category)
        ]

    def _replace_long_term_facts_locked(self, category: str, facts: list[str]) -> bool:
        current_facts = self._read_long_term_facts_locked(category)
        if current_facts == facts:
            return False
        self._tbl.delete(f"type = 'long_term' AND category = '{category}'")
        if facts:
            updated_at = datetime.now().isoformat()
            self._tbl.add(
                [
                    self._make_row(
                        key=self._long_term_fact_key(category, updated_at, idx),
                        content=fact,
                        type_="long_term",
                        category=category,
                        updated_at=updated_at,
                    )
                    for idx, fact in enumerate(facts, start=1)
                ]
            )
        self._invalidate_retrieval_index()
        return True

    def _normalize_long_term_fact_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        max_chars: int,
    ) -> list[dict[str, Any]]:
        if max_chars <= 0:
            return []
        normalized_rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        used = 0
        for row in rows:
            fact = str(row.get("content", "")).strip()
            if not fact or fact in seen:
                continue
            prefix = 1 if normalized_rows else 0
            remaining = max_chars - used - prefix
            if remaining <= 0:
                break
            if len(fact) > remaining:
                if remaining <= 1:
                    break
                fact = fact[: remaining - 1].rstrip() + "…"
            if not fact or fact in seen:
                continue
            next_row = dict(row)
            next_row["content"] = fact
            normalized_rows.append(next_row)
            seen.add(fact)
            used += len(fact) + prefix
        return normalized_rows

    def _write_long_term_fact_rows_locked(self, category: str, rows: list[dict[str, Any]]) -> bool:
        current_rows = self._read_long_term_fact_rows_locked(category)
        normalized_rows = [dict(row) for row in rows if str(row.get("content", "")).strip()]
        if current_rows == normalized_rows:
            return False
        self._tbl.delete(f"type = 'long_term' AND category = '{category}'")
        if normalized_rows:
            self._tbl.add(normalized_rows)
        self._invalidate_retrieval_index()
        return True

    def _embed_long_term_aggregate(self) -> None:
        aggregated = self.read_long_term()
        if aggregated:
            self._embed_and_store(
                key="long_term_aggregate",
                content=aggregated,
                type_="long_term",
            )
            return
        if not self._vec_tbl:
            return
        try:
            with self._store_lock:
                rows = self._tbl.search().where("type = 'long_term'").limit(200).to_list()
                has_content = any(row.get("content", "").strip() for row in rows) if rows else False
                if not has_content and self._vec_tbl:
                    self._delete_vector_by_key("long_term_aggregate")
        except Exception as exc:
            logger.warning("⚠️ 长期向量清理失败 / long-term vector clear failed: {}", exc)

    def _schedule_long_term_embedding(self) -> None:
        if not self._embed_fn or not self._vec_tbl:
            return

        fut = self._MEMORY_BG_EXECUTOR.submit(self._embed_long_term_aggregate)

        def _log_if_failed(future: Any) -> None:
            try:
                future.result()
            except Exception as exc:
                logger.warning("⚠️ 长期向量异步更新失败 / async long-term embedding failed: {}", exc)

        fut.add_done_callback(_log_if_failed)
