from __future__ import annotations

from typing import Any

from loguru import logger

from bao.agent._memory_shared import _MIGRATION_CHUNK_SIZE, _SAMPLE
from bao.utils.db import ensure_table


class _MemoryStoreSchemaMixin:
    def _ensure_migrated_table(self):
        try:
            tbl = self._db.open_table("memory")
            probe = tbl.search().limit(1).to_list()
            if probe and "quality" not in probe[0]:
                return self._migrate_schema(tbl)
            if probe and "hit_count" not in probe[0]:
                return self._backfill_new_columns(tbl)
            return tbl
        except Exception:
            return ensure_table(self._db, "memory", list(_SAMPLE))

    def _migrate_schema(self, old_tbl):
        try:
            rows = old_tbl.search().to_list()
            try:
                self._db.drop_table("memory_migrated")
            except Exception:
                pass

            self._db.create_table("memory_migrated", data=list(_SAMPLE))
            staged = self._db.open_table("memory_migrated")
            staged.delete("key = '_init_'")

            batch: list[dict[str, Any]] = []
            migrated_count = 0
            source_rows = rows or list(_SAMPLE)
            for row in source_rows:
                new_row = self._migrate_schema_row(row)
                batch.append(new_row)
                if len(batch) >= _MIGRATION_CHUNK_SIZE:
                    staged.add(batch)
                    migrated_count += len(batch)
                    batch = []
            if batch:
                staged.add(batch)
                migrated_count += len(batch)

            staged_rows = staged.search().to_list()
            self._db.drop_table("memory")
            tbl = self._db.create_table("memory", data=staged_rows)
            self._db.drop_table("memory_migrated")
            try:
                self._db.drop_table("memory_vectors")
            except Exception:
                pass
            self._invalidate_retrieval_index()
            logger.info("🔀 迁移结构 / schema migrated: {} rows", migrated_count)
            return tbl
        except Exception as exc:
            logger.error("❌ 迁移失败 / schema migration failed: {}", exc)
            return old_tbl

    def _migrate_schema_row(self, row: dict[str, Any]) -> dict[str, Any]:
        new_row = {
            "key": row.get("key", ""),
            "content": row.get("content", ""),
            "type": row.get("type", ""),
            "updated_at": row.get("updated_at", ""),
            "category": "",
            "quality": 0,
            "uses": 0,
            "successes": 0,
            "outcome": "",
            "deprecated": False,
            "last_hit_at": "",
            "hit_count": 0,
        }
        if row.get("type") == "long_term":
            new_row["category"] = "general"
            if new_row["key"] == "long_term":
                new_row["key"] = "long_term_general"
        if row.get("type") != "experience":
            return new_row

        content = str(row.get("content", ""))
        new_row["deprecated"] = content.startswith("[Deprecated]")
        if new_row["deprecated"]:
            content = content[len("[Deprecated]") :].strip()
        new_row["quality"] = self._parse_field_int(content, "Quality", 3)
        new_row["uses"] = self._parse_field_int(content, "Uses", 0)
        new_row["successes"] = self._parse_field_int(content, "Successes", 0)
        new_row["category"] = self._parse_field_str(content, "Category") or "general"
        new_row["outcome"] = self._parse_field_str(content, "Outcome") or ""
        task = self._parse_field_str(content, "Task")
        lessons = self._parse_field_str(content, "Lessons")
        keywords = self._parse_field_str(content, "Keywords")
        trace = self._parse_field_str(content, "Trace")
        parts = []
        if task:
            parts.append(f"Task: {task}")
        if lessons:
            parts.append(f"Lessons: {lessons}")
        if keywords:
            parts.append(f"Keywords: {keywords}")
        if trace:
            parts.append(f"Trace: {trace}")
        new_row["content"] = "\n".join(parts) if parts else content
        return new_row

    def _backfill_new_columns(self, tbl):
        try:
            rows = tbl.search().to_list()
            try:
                self._db.drop_table("memory_backfill")
            except Exception:
                pass

            self._db.create_table("memory_backfill", data=list(_SAMPLE))
            staged = self._db.open_table("memory_backfill")
            staged.delete("key = '_init_'")

            batch: list[dict[str, Any]] = []
            patched_count = 0
            source_rows = rows or list(_SAMPLE)
            for row in source_rows:
                next_row = dict(row)
                next_row.setdefault("last_hit_at", "")
                next_row.setdefault("hit_count", 0)
                next_row.pop("_distance", None)
                next_row.pop("_relevance_score", None)
                next_row.pop("vector", None)
                batch.append(next_row)
                if len(batch) >= _MIGRATION_CHUNK_SIZE:
                    staged.add(batch)
                    patched_count += len(batch)
                    batch = []
            if batch:
                staged.add(batch)
                patched_count += len(batch)

            staged_rows = staged.search().to_list()
            self._db.drop_table("memory")
            tbl = self._db.create_table("memory", data=staged_rows)
            self._db.drop_table("memory_backfill")
            self._invalidate_retrieval_index()
            logger.info("🔀 补齐新列 / backfilled new columns: {} rows", patched_count)
            return tbl
        except Exception as exc:
            logger.error("❌ 补齐新列失败 / backfill failed: {}", exc)
            return tbl

    @staticmethod
    def _parse_field_int(content: str, field: str, default: int = 0) -> int:
        for line in content.split("\n"):
            if line.startswith(f"[{field}]"):
                try:
                    return int(line.split("]", 1)[1].strip())
                except (ValueError, IndexError):
                    pass
        return default

    @staticmethod
    def _parse_field_str(content: str, field: str) -> str:
        for line in content.split("\n"):
            if line.startswith(f"[{field}]"):
                return line.split("]", 1)[1].strip()
        return ""
