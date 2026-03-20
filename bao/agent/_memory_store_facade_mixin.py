from __future__ import annotations

from datetime import datetime

from bao.agent._memory_experience_models import ExperienceAppendRequest, ExperienceListRequest


class _MemoryStoreFacadeMixin:
    def read_long_term(self, category: str | None = None) -> str:
        return self._long_term().read_long_term(category)

    def list_long_term_entries(self) -> list[dict[str, str]]:
        return self._long_term().list_long_term_entries()

    def list_memory_categories(self) -> list[dict[str, object]]:
        return self._long_term().list_memory_categories()

    def get_memory_category(self, category: str) -> dict[str, object] | None:
        return self._long_term().get_memory_category(category)

    def list_memory_facts(self, category: str) -> list[dict[str, object]]:
        return self._long_term().list_memory_facts(category)

    def upsert_memory_fact(
        self,
        category: str,
        content: str,
        *,
        key: str = "",
    ) -> dict[str, object] | None:
        return self._long_term().upsert_memory_fact(category, content, key=key)

    def delete_memory_fact(self, category: str, key: str) -> dict[str, object] | None:
        return self._long_term().delete_memory_fact(category, key)

    def exists_long_term_key(self, key: str) -> bool:
        return self._long_term().exists_long_term_key(key)

    def delete_long_term_by_key(self, key: str) -> bool:
        deleted = self._long_term().delete_long_term_by_key(key)
        if deleted:
            self._schedule_long_term_embedding()
            self._emit_change(scope="long_term", operation="delete_entry", key=key)
        return deleted

    def write_long_term(self, content: str, category: str = "general") -> None:
        self._long_term().write_long_term(content, category)

    def append_memory_category(self, category: str, content: str) -> dict[str, object] | None:
        return self._long_term().append_memory_category(category, content)

    def clear_memory_category(self, category: str) -> dict[str, object] | None:
        return self._long_term().clear_memory_category(category)

    def write_categorized_memory(self, updates: dict[str, object]) -> None:
        self._long_term().write_categorized_memory(updates)

    def append_history(self, entry: str) -> None:
        cleaned = entry.rstrip()
        with self._store_lock:
            ts = datetime.now().isoformat()
            row_key = f"history_{ts}"
            self._tbl.add(
                [
                    self._make_row(
                        key=row_key,
                        content=cleaned,
                        type_="history",
                        updated_at=ts,
                    )
                ]
            )
            self._invalidate_retrieval_index()
        self._embed_and_store(key=row_key, content=cleaned, type_="history")

    def embed_long_term_aggregate(self) -> None:
        self._embed_long_term_aggregate()

    def search_memory(
        self,
        query: str,
        limit: int = 5,
        *,
        query_context=None,
    ) -> list[str]:
        return self._recall().search_memory(query, limit=limit, query_context=query_context)

    def append_experience(self, request: ExperienceAppendRequest) -> None:
        self._experience().append_experience(request)

    def search_experience(
        self,
        query: str,
        limit: int = 3,
        *,
        query_context=None,
    ) -> list[str]:
        return self._experience().search_experience(query, limit=limit, query_context=query_context)

    def list_experience_items(
        self,
        request: ExperienceListRequest,
    ) -> list[dict[str, object]]:
        return self._experience().list_experience_items(request)

    def get_experience_item(self, key: str) -> dict[str, object] | None:
        return self._experience().get_experience_item(key)

    def set_experience_deprecated(self, key: str, deprecated: bool) -> bool:
        return self._experience().set_experience_deprecated(key, deprecated)

    def delete_experience(self, key: str) -> bool:
        return self._experience().delete_experience(key)

    def promote_experience_to_memory(
        self,
        key: str,
        category: str = "project",
    ) -> dict[str, object] | None:
        return self._experience().promote_experience_to_memory(key, category)

    def deprecate_similar(self, task_desc: str) -> int:
        return self._experience().deprecate_similar(task_desc)

    def boost_experience(self, task_desc: str, delta: int = 1) -> int:
        return self._experience().boost_experience(task_desc, delta=delta)

    def record_reuse(self, task_desc: str, success: bool) -> int:
        return self._experience().record_reuse(task_desc, success)

    def cleanup_stale(self, max_deprecated_days: int = 30, max_low_quality_days: int = 90) -> int:
        return self._experience().cleanup_stale(
            max_deprecated_days=max_deprecated_days,
            max_low_quality_days=max_low_quality_days,
        )

    def get_merge_candidates(self, min_count: int = 5) -> list[list[str]]:
        from loguru import logger

        with self._store_lock:
            try:
                rows = self._tbl.search().where("type = 'experience'").limit(200).to_list()
                active = [row for row in rows if not row.get("deprecated")]
                if len(active) < min_count:
                    return []
                groups: dict[str, list[str]] = {}
                for row in active:
                    groups.setdefault(row.get("category") or "general", []).append(row.get("content") or "")
                return [entries for entries in groups.values() if len(entries) >= 3]
            except Exception as exc:
                logger.warning("⚠️ 候选检索失败 / merge candidates failed: {}", exc)
                return []

    def replace_merged(
        self,
        old_entries: list[str],
        merged_content: str,
        *,
        category: str = "general",
        quality: int = 4,
    ) -> None:
        from loguru import logger

        with self._store_lock:
            try:
                rows = self._tbl.search().where("type = 'experience'").limit(200).to_list()
                content_to_key = {row.get("content"): row.get("key") for row in rows}
                for entry in old_entries:
                    if key := content_to_key.get(entry):
                        self._tbl.delete(f"key = '{key}'")
                        self._delete_vector_by_key(key)
                ts = datetime.now().isoformat()
                merged_key = f"experience_merged_{ts}"
                self._tbl.add(
                    [
                        self._make_row(
                            key=merged_key,
                            content=merged_content,
                            type_="experience",
                            category=category,
                            quality=quality,
                            updated_at=ts,
                        )
                    ]
                )
                self._invalidate_retrieval_index()
                logger.info("🔀 合并经验 / experiences merged: {} into 1", len(old_entries))
            except Exception as exc:
                logger.warning("⚠️ 合并经验失败 / experience merge failed: {}", exc)
                return
        self._embed_and_store(key=merged_key, content=merged_content, type_="experience")

    def get_memory_context(self, max_chars: int | None = None) -> str:
        return self._long_term().get_memory_context(max_chars=max_chars)

    def get_relevant_memory_context(
        self,
        query: str,
        max_chars: int | None = None,
        *,
        query_context=None,
    ) -> str:
        return self._long_term().get_relevant_memory_context(
            query,
            max_chars=max_chars,
            query_context=query_context,
        )

    def remember(self, content: str, category: str = "general") -> str:
        return self._long_term().remember(content, category)

    def forget(self, query: str) -> str:
        return self._long_term().forget(query)

    def update_memory(self, category: str, content: str) -> str:
        return self._long_term().update_memory(category, content)

    def recall(
        self,
        query: str,
        *,
        related_limit: int = 5,
        experience_limit: int = 3,
        long_term_chars: int | None = None,
        include_long_term: bool = True,
    ):
        return self._recall().recall(
            query,
            related_limit=related_limit,
            experience_limit=experience_limit,
            long_term_chars=long_term_chars,
            include_long_term=include_long_term,
        )
