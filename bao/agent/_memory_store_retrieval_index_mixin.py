from __future__ import annotations

from typing import Any

from bao.agent._memory_shared import MEMORY_CATEGORIES


class _MemoryStoreRetrievalIndexMixin:
    @staticmethod
    def _backfill_scan_limit() -> int:
        from bao.agent import memory as memory_module

        return int(getattr(memory_module, "_BACKFILL_SCAN_LIMIT", 1000))

    def _get_retrieval_index(self) -> dict[str, Any]:
        self._ensure_retrieval_state()
        with self._store_lock:
            cached = self._retrieval_index
            if isinstance(cached, dict) and cached.get("revision") == self._retrieval_revision:
                return cached

            rows = (
                self._tbl.search()
                .where("type != '_init_'")
                .limit(self._backfill_scan_limit())
                .to_list()
            )
            state = self._build_retrieval_index_state()
            for raw in rows:
                self._consume_retrieval_index_row(state, raw)
            index = {
                "revision": self._retrieval_revision,
                "all_rows": state["all_rows"],
                "memory_rows": state["memory_rows"],
                "experience_rows": state["experience_rows"],
                "row_by_key": state["row_by_key"],
                "row_by_content_type": state["row_by_content_type"],
                "row_tokens_by_key": state["row_tokens_by_key"],
                "row_tokens_by_content_type": state["row_tokens_by_content_type"],
                "experience_by_content": state["experience_by_content"],
                "experience_tokens_by_key": state["experience_tokens_by_key"],
                "long_term_parts": self._build_long_term_parts(state["long_term_rows_by_category"]),
                "long_term_tokens_by_category": state["long_term_tokens_by_category"],
            }
            self._retrieval_index = index
            return index

    def _build_retrieval_index_state(self) -> dict[str, Any]:
        return {
            "all_rows": [],
            "memory_rows": [],
            "experience_rows": [],
            "row_by_key": {},
            "row_by_content_type": {},
            "row_tokens_by_key": {},
            "row_tokens_by_content_type": {},
            "experience_by_content": {},
            "experience_tokens_by_key": {},
            "long_term_rows_by_category": {category: [] for category in MEMORY_CATEGORIES},
            "long_term_tokens_by_category": {category: set() for category in MEMORY_CATEGORIES},
        }

    def _consume_retrieval_index_row(self, state: dict[str, Any], raw: dict[str, Any]) -> None:
        row = dict(raw)
        type_ = str(row.get("type") or "")
        if not type_ or type_ == "_init_":
            return
        key = str(row.get("key") or "")
        content = str(row.get("content") or "")
        tokens = tuple(self._tokenize(content)) if content else ()

        state["all_rows"].append(row)
        if key:
            state["row_by_key"][key] = row
            if tokens:
                state["row_tokens_by_key"][key] = tokens
        if content:
            content_type = (content, type_)
            state["row_by_content_type"][content_type] = row
            if tokens:
                state["row_tokens_by_content_type"][content_type] = tokens

        if type_ == "experience":
            state["experience_rows"].append(row)
            if content:
                state["experience_by_content"][content] = row
            if key and tokens:
                state["experience_tokens_by_key"][key] = tokens
            return

        if type_ == "long_term":
            self._consume_long_term_index_row(state, row, key, content, tokens)
            return
        state["memory_rows"].append(row)

    def _consume_long_term_index_row(
        self,
        state: dict[str, Any],
        row: dict[str, Any],
        key: str,
        content: str,
        tokens: tuple[str, ...],
    ) -> None:
        category = str(row.get("category") or "general")
        text = content.strip()
        if category not in state["long_term_rows_by_category"] or not text:
            return
        state["long_term_rows_by_category"][category].append(
            (str(row.get("updated_at", "")), key, text)
        )
        if tokens:
            state["long_term_tokens_by_category"][category].update(tokens)

    def _build_long_term_parts(
        self,
        rows_by_category: dict[str, list[tuple[str, str, str]]],
    ) -> list[tuple[str, str]]:
        return [
            (
                category,
                self._join_memory_facts(
                    [
                        text
                        for _, _, text in sorted(
                            rows_by_category[category],
                            key=lambda item: (item[0], item[1]),
                        )
                    ]
                ),
            )
            for category in MEMORY_CATEGORIES
            if rows_by_category[category]
        ]

    @staticmethod
    def _escape_where_value(value: str) -> str:
        return value.replace("'", "''")

    def _lookup_rows_by_keys(
        self,
        keys: list[str],
        *,
        type_filter: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for key in dict.fromkeys(str(key or "") for key in keys):
            if not key:
                continue
            key_safe = self._escape_where_value(key)
            where = f"key = '{key_safe}'"
            if type_filter:
                where = f"type = '{type_filter}' AND {where}"
            rows = self._tbl.search().where(where).limit(1).to_list()
            if rows:
                found[key] = dict(rows[0])
        return found

    def _lookup_row_by_content_type(self, content: str, type_: str) -> dict[str, Any] | None:
        text = str(content or "")
        kind = str(type_ or "")
        if not text or not kind:
            return None
        text_safe = self._escape_where_value(text)
        type_safe = self._escape_where_value(kind)
        rows = (
            self._tbl.search()
            .where(f"type = '{type_safe}' AND content = '{text_safe}'")
            .limit(1)
            .to_list()
        )
        return dict(rows[0]) if rows else None

    def _resolve_index_rows(
        self,
        index: dict[str, Any],
        *,
        vec_rows: list[dict[str, Any]],
        content_map_key: str,
        type_filter: str | None = None,
    ) -> tuple[dict[str, dict[str, Any]], dict[Any, dict[str, Any]]]:
        key_map = dict(index["row_by_key"])
        content_map = dict(index[content_map_key])
        missing_keys = [
            key
            for key in (str(row.get("key", "") or "") for row in vec_rows)
            if key and key not in key_map
        ]
        if missing_keys:
            key_map.update(self._lookup_rows_by_keys(missing_keys, type_filter=type_filter))
        return key_map, content_map

    def _patch_cached_retrieval_row(self, row: dict[str, Any]) -> None:
        self._ensure_retrieval_state()
        cached = self._retrieval_index
        if not isinstance(cached, dict) or cached.get("revision") != self._retrieval_revision:
            return

        key = str(row.get("key") or "")
        if not key:
            return
        existing = cached["row_by_key"].get(key)
        if existing is None:
            return

        row_copy = dict(row)
        type_ = str(row_copy.get("type") or "")
        content = str(row_copy.get("content") or "")
        cached["row_by_key"][key] = row_copy
        if content:
            cached["row_by_content_type"][(content, type_)] = row_copy
            if type_ == "experience":
                cached["experience_by_content"][content] = row_copy

        for bucket_name in ("all_rows", "experience_rows", "memory_rows"):
            bucket = cached[bucket_name]
            for index, item in enumerate(bucket):
                if str(item.get("key") or "") == key:
                    bucket[index] = row_copy
                    break

    def _retrieval_rows(
        self,
        index: dict[str, Any],
        *,
        type_filter: str | None = None,
        exclude_types: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if type_filter == "experience":
            rows = index["experience_rows"]
        elif type_filter is not None:
            rows = [row for row in index["all_rows"] if str(row.get("type") or "") == type_filter]
        elif exclude_types:
            excluded = set(exclude_types)
            if excluded == {"experience", "long_term"}:
                rows = index["memory_rows"]
            else:
                rows = [
                    row for row in index["all_rows"] if str(row.get("type") or "") not in excluded
                ]
        else:
            rows = index["all_rows"]
        return rows[:limit]

    def _row_tokens_from_index(
        self,
        row: dict[str, Any],
        index: dict[str, Any],
    ) -> tuple[str, ...]:
        key = str(row.get("key") or "")
        if key and key in index["row_tokens_by_key"]:
            return index["row_tokens_by_key"][key]
        content = str(row.get("content") or "")
        type_ = str(row.get("type") or "")
        content_type = (content, type_)
        if content and content_type in index["row_tokens_by_content_type"]:
            return index["row_tokens_by_content_type"][content_type]
        tokens = tuple(self._tokenize(content))
        if not tokens or not content:
            return tokens
        if key:
            index["row_tokens_by_key"][key] = tokens
            if type_ == "experience":
                index["experience_tokens_by_key"][key] = tokens
        index["row_tokens_by_content_type"][content_type] = tokens
        return tokens
