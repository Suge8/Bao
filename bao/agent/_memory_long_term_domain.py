from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from ._memory_shared import MEMORY_CATEGORIES, _RecallQueryContext

if TYPE_CHECKING:
    from bao.agent.memory import MemoryStore


class _LongTermMemoryDomain:
    def __init__(self, host: "MemoryStore"):
        self._host = host

    def read_long_term(self, category: str | None = None) -> str:
        with self._host._store_lock:
            try:
                if category:
                    return self._host._join_memory_facts(self._host._read_long_term_facts_locked(category))
                parts = []
                for cat in MEMORY_CATEGORIES:
                    content = self._host._join_memory_facts(self._host._read_long_term_facts_locked(cat))
                    if content:
                        parts.append(f"[{cat}] {content}")
                return "\n".join(parts)
            except Exception:
                return ""

    def list_long_term_entries(self) -> list[dict[str, str]]:
        return [
            {"key": str(item.get("key") or ""), "category": str(item.get("category") or "general"), "content": str(item.get("content") or "")}
            for item in self.list_memory_categories()
            if str(item.get("content") or "").strip()
        ]

    def list_memory_categories(self) -> list[dict[str, Any]]:
        with self._host._store_lock:
            try:
                rows = self._host._read_long_term_rows_locked()
            except Exception:
                rows = []
        by_category: dict[str, list[dict[str, Any]]] = {category: [] for category in MEMORY_CATEGORIES}
        for row in rows:
            category = str(row.get("category") or "general")
            if category in by_category and str(row.get("content", "")).strip():
                by_category[category].append(dict(row))
        items: list[dict[str, Any]] = []
        for category in MEMORY_CATEGORIES:
            fact_rows = sorted(by_category.get(category, []), key=lambda row: str(row.get("key") or ""))
            facts = [str(row.get("content", "")).strip() for row in fact_rows]
            content = self._host._join_memory_facts(facts)
            latest = max((str(row.get("updated_at", "")) for row in fact_rows), default="")
            preview = content.replace("\n", " ")[:160]
            if len(content.replace("\n", " ")) > 160:
                preview += "…"
            items.append(
                {
                    "key": f"long_term_{category}",
                    "category": category,
                    "content": content,
                    "preview": preview,
                    "updated_at": latest,
                    "char_count": len(content),
                    "line_count": len(facts),
                    "fact_count": len(facts),
                    "facts": [
                        {
                            "key": str(row.get("key") or ""),
                            "content": str(row.get("content") or "").strip(),
                            "updated_at": str(row.get("updated_at") or ""),
                            "hit_count": int(row.get("hit_count", 0) or 0),
                            "last_hit_at": str(row.get("last_hit_at") or ""),
                        }
                        for row in fact_rows
                        if str(row.get("content", "")).strip()
                    ],
                    "is_empty": not bool(content),
                }
            )
        return items

    def get_memory_category(self, category: str) -> dict[str, Any] | None:
        if category not in MEMORY_CATEGORIES:
            return None
        for item in self.list_memory_categories():
            if item.get("category") == category:
                return item
        return None

    def list_memory_facts(self, category: str) -> list[dict[str, Any]]:
        if category not in MEMORY_CATEGORIES:
            return []
        detail = self.get_memory_category(category)
        facts = detail.get("facts") if isinstance(detail, dict) else None
        return [dict(item) for item in facts] if isinstance(facts, list) else []

    def upsert_memory_fact(self, category: str, content: str, *, key: str = "") -> dict[str, Any] | None:
        if category not in MEMORY_CATEGORIES:
            return None
        new_facts = self._host._normalize_memory_facts(content, max_chars=self._host._memory_cap(category))
        if not new_facts:
            return self.get_memory_category(category)
        replacement = new_facts[0]
        with self._host._store_lock:
            fact_rows = [dict(row) for row in self._host._read_long_term_fact_rows_locked(category)]
            updated_at = datetime.now().isoformat()
            next_rows = [dict(row) for row in fact_rows]
            if key:
                for index, row in enumerate(next_rows):
                    if str(row.get("key") or "") != key:
                        continue
                    next_rows[index] = self._host._make_row(
                        key=key,
                        content=replacement,
                        type_="long_term",
                        category=category,
                        updated_at=updated_at,
                        last_hit_at=str(row.get("last_hit_at") or ""),
                        hit_count=int(row.get("hit_count", 0) or 0),
                    )
                    break
                else:
                    return self.get_memory_category(category)
            else:
                next_rows.append(
                    self._host._make_row(
                        key=self._host._long_term_fact_key(category, updated_at, len(next_rows) + 1),
                        content=replacement,
                        type_="long_term",
                        category=category,
                        updated_at=updated_at,
                    )
                )
            normalized_rows = self._host._normalize_long_term_fact_rows(next_rows, max_chars=self._host._memory_cap(category))
            changed = self._host._write_long_term_fact_rows_locked(category, normalized_rows)
        if changed:
            self._host._embed_long_term_aggregate()
            self._host._emit_change(scope="long_term", operation="update_fact" if key else "append_fact", category=category, key=key)
        return self.get_memory_category(category)

    def delete_memory_fact(self, category: str, key: str) -> dict[str, Any] | None:
        if category not in MEMORY_CATEGORIES or not key:
            return None
        with self._host._store_lock:
            fact_rows = [dict(row) for row in self._host._read_long_term_fact_rows_locked(category)]
            kept_rows = [row for row in fact_rows if str(row.get("key") or "") != key]
            normalized_rows = self._host._normalize_long_term_fact_rows(kept_rows, max_chars=self._host._memory_cap(category))
            changed = self._host._write_long_term_fact_rows_locked(category, normalized_rows)
        if changed:
            self._host._embed_long_term_aggregate()
            self._host._emit_change(scope="long_term", operation="delete_fact", category=category, key=key)
        return self.get_memory_category(category)

    def exists_long_term_key(self, key: str) -> bool:
        if not key:
            return False
        if key.startswith("long_term_"):
            category = key.removeprefix("long_term_")
            if category in MEMORY_CATEGORIES:
                return bool(self.read_long_term(category).strip())
        key_safe = key.replace("'", "''")
        with self._host._store_lock:
            try:
                rows = self._host._tbl.search().where(f"type = 'long_term' AND key = '{key_safe}'").limit(1).to_list()
                return bool(rows)
            except Exception:
                return False

    def delete_long_term_by_key(self, key: str) -> bool:
        if not key:
            return False
        if key.startswith("long_term_"):
            category = key.removeprefix("long_term_")
            if category in MEMORY_CATEGORIES:
                return self.clear_memory_category(category) is not None
        key_safe = key.replace("'", "''")
        with self._host._store_lock:
            try:
                rows = self._host._tbl.search().where(f"type = 'long_term' AND key = '{key_safe}'").limit(1).to_list()
                if not rows:
                    return False
                self._host._tbl.delete(f"type = 'long_term' AND key = '{key_safe}'")
                self._host._invalidate_retrieval_index()
                return True
            except Exception as exc:
                logger.warning("⚠️ 按键删除失败 / delete by key failed: {}", exc)
                return False

    def write_long_term(self, content: str, category: str = "general") -> None:
        if category not in MEMORY_CATEGORIES:
            category = "general"
        facts = self._host._normalize_memory_facts(content, max_chars=self._host._memory_cap(category))
        with self._host._store_lock:
            changed = self._host._replace_long_term_facts_locked(category, facts)
        if changed:
            self._host._schedule_long_term_embedding()
            self._host._emit_change(scope="long_term", operation="replace_category", category=category)

    def append_memory_category(self, category: str, content: str) -> dict[str, Any] | None:
        if category not in MEMORY_CATEGORIES:
            return None
        self.remember(content, category)
        return self.get_memory_category(category)

    def clear_memory_category(self, category: str) -> dict[str, Any] | None:
        if category not in MEMORY_CATEGORIES:
            return None
        self.write_long_term("", category)
        return self.get_memory_category(category)

    def write_categorized_memory(self, updates: dict[str, Any]) -> None:
        changed_any = False
        with self._host._store_lock:
            for cat, content in updates.items():
                if cat not in MEMORY_CATEGORIES or (content is not None and not isinstance(content, (str, list))):
                    continue
                facts = self._host._normalize_memory_facts(content or "", max_chars=self._host._memory_cap(cat))
                if self._host._replace_long_term_facts_locked(cat, facts):
                    changed_any = True
        if changed_any:
            self._host._schedule_long_term_embedding()
            self._host._emit_change(scope="long_term", operation="replace_categories", category="all")

    def get_memory_context(self, max_chars: int | None = None) -> str:
        return self._host._format_long_term_parts(self._host._collect_long_term_parts(), max_chars=max_chars)

    def get_relevant_memory_context(
        self,
        query: str,
        max_chars: int | None = None,
        *,
        query_context: _RecallQueryContext | None = None,
    ) -> str:
        query_ctx = query_context or self._host._build_recall_query_context(query, include_vectors=False)
        if query_ctx is None or not query_ctx.query_term_set:
            return ""
        parts = self._host._collect_long_term_parts(query_tokens=query_ctx.query_term_set)
        return self._host._format_long_term_parts(parts, max_chars=max_chars)

    def remember(self, content: str, category: str = "general") -> str:
        if category not in MEMORY_CATEGORIES:
            category = "general"
        new_facts = self._host._normalize_memory_facts(content, max_chars=self._host._memory_cap(category))
        if not new_facts:
            return f"Remembered in [{category}]: "
        with self._host._store_lock:
            current_facts = self._host._read_long_term_facts_locked(category)
            merged = self._host._normalize_memory_facts(current_facts + new_facts, max_chars=self._host._memory_cap(category))
            changed = self._host._replace_long_term_facts_locked(category, merged)
        if changed:
            self._host._embed_long_term_aggregate()
            self._host._emit_change(scope="long_term", operation="append_fact", category=category)
        return f"Remembered in [{category}]: {content[:80]}"

    def forget(self, query: str) -> str:
        removed = 0
        changed = False
        with self._host._store_lock:
            try:
                rows = self._host._read_long_term_rows_locked()
                query_lower = query.lower()
                for category in MEMORY_CATEGORIES:
                    facts = []
                    kept_facts = []
                    for row in rows:
                        if str(row.get("category") or "general") != category:
                            continue
                        fact = str(row.get("content") or "").strip()
                        if not fact:
                            continue
                        facts.append(fact)
                        if query_lower in fact.lower():
                            removed += 1
                            continue
                        kept_facts.append(fact)
                    if facts != kept_facts and self._host._replace_long_term_facts_locked(category, kept_facts):
                        changed = True
            except Exception as exc:
                logger.warning("⚠️ 遗忘失败 / forget failed: {}", exc)
        if changed:
            self._host._embed_long_term_aggregate()
            self._host._emit_change(scope="long_term", operation="forget", category="all")
        return f"Removed {removed} memory entries matching '{query[:40]}'."

    def update_memory(self, category: str, content: str) -> str:
        if category not in MEMORY_CATEGORIES:
            return f"Invalid category. Use one of: {', '.join(MEMORY_CATEGORIES)}"
        facts = self._host._normalize_memory_facts(content, max_chars=self._host._memory_cap(category))
        with self._host._store_lock:
            changed = self._host._replace_long_term_facts_locked(category, facts)
        if changed:
            self._host._embed_long_term_aggregate()
            self._host._emit_change(scope="long_term", operation="update_category", category=category)
        return f"Updated [{category}] memory."
