"""Memory system — LanceDB backend."""

from __future__ import annotations

import os
from datetime import datetime
from math import exp
from pathlib import Path
from typing import Any

from loguru import logger

from bao.utils.db import get_db, ensure_table

_SAMPLE = [{"key": "_init_", "content": "", "type": "long_term", "updated_at": ""}]

_ENV_KEY = "BAO_EMBEDDING_API_KEY"
_ENV_BASE = "BAO_EMBEDDING_BASE_URL"


class MemoryStore:
    def __init__(self, workspace: Path, embedding_config: Any | None = None):
        self._db = get_db(workspace)
        self._tbl = ensure_table(self._db, "memory", _SAMPLE)
        self._embed_fn = None
        self._vec_tbl = None
        if embedding_config and getattr(embedding_config, "enabled", False):
            self._init_embedding(embedding_config)
        self._migrate_legacy(workspace)

    def _init_embedding(self, cfg: Any) -> None:
        try:
            from lancedb.embeddings import get_registry

            registry = get_registry()
            backend, kwargs = self._resolve_embedding_backend(registry, cfg)
            self._embed_fn = registry.get(backend).create(**kwargs)
            # Probe actual dim with a test embedding (some backends report wrong ndims)
            probe = self._embed_fn.compute_source_embeddings(["dim probe"])
            ndim = len(probe[0])
            self._vec_tbl = ensure_table(
                self._db,
                "memory_vectors",
                [{"content": "", "type": "long_term", "vector": [0.0] * ndim}],
            )
            logger.debug("Embedding enabled: {} via {} (dim={})", cfg.model, backend, ndim)
            self._backfill_embeddings()
        except Exception as e:
            logger.warning("Embedding init failed: {}", e)
            self._embed_fn = None

    @staticmethod
    def _resolve_embedding_backend(registry: Any, cfg: Any) -> tuple[str, dict[str, Any]]:
        model = cfg.model.lower()
        if "gemini" in model or "models/embedding" in model:
            os.environ["GOOGLE_API_KEY"] = cfg.api_key
            name = cfg.model if cfg.model.startswith("models/") else f"models/{cfg.model}"
            return "gemini-text", {"name": name}
        # LanceDB requires `$var:` references for sensitive keys, resolved via registry
        registry.set_var(_ENV_KEY, cfg.api_key)
        kwargs: dict[str, Any] = {"name": cfg.model, "api_key": f"$var:{_ENV_KEY}"}
        if cfg.base_url:
            registry.set_var(_ENV_BASE, cfg.base_url)
            kwargs["base_url"] = f"$var:{_ENV_BASE}"
        if getattr(cfg, "dim", 0) > 0:
            kwargs["dim"] = cfg.dim
        return "openai", kwargs

    def _backfill_embeddings(self) -> None:
        if not self._embed_fn or not self._vec_tbl:
            return
        try:
            if any(v.get("content", "").strip() for v in self._vec_tbl.search().limit(2).to_list()):
                return
            rows = self._tbl.search().where("type != '_init_'").limit(500).to_list()
            count = 0
            for r in rows:
                content = r.get("content", "").strip()
                type_ = r.get("type", "")
                if not content or not type_:
                    continue
                try:
                    vec = self._embed_fn.compute_source_embeddings([content])[0]
                    self._vec_tbl.add([{"content": content, "type": type_, "vector": vec}])
                    count += 1
                except Exception:
                    continue
            if count:
                logger.info("Backfilled {} existing records with embeddings", count)
        except Exception as e:
            logger.warning("Embedding backfill failed: {}", e)

    def _migrate_legacy(self, workspace: Path) -> None:
        mem_file = workspace / "memory" / "MEMORY.md"
        hist_file = workspace / "memory" / "HISTORY.md"
        if mem_file.exists():
            existing = self._tbl.search().where("key = 'long_term'").limit(1).to_list()
            if not existing:
                self.write_long_term(mem_file.read_text(encoding="utf-8"))
            mem_file.rename(mem_file.with_suffix(".md.migrated"))
        if hist_file.exists():
            existing = self._tbl.search().where("type = 'history'").limit(1).to_list()
            if not existing:
                for entry in hist_file.read_text(encoding="utf-8").strip().split("\n\n"):
                    if entry.strip():
                        self.append_history(entry.strip())
            hist_file.rename(hist_file.with_suffix(".md.migrated"))

    def read_long_term(self) -> str:
        try:
            rows = self._tbl.search().where("key = 'long_term'").limit(1).to_list()
            return rows[0]["content"] if rows else ""
        except Exception:
            return ""

    def write_long_term(self, content: str) -> None:
        self._tbl.delete("key = 'long_term'")
        self._tbl.add(
            [
                {
                    "key": "long_term",
                    "content": content,
                    "type": "long_term",
                    "updated_at": datetime.now().isoformat(),
                }
            ]
        )
        self._embed_and_store(content, "long_term")

    def append_history(self, entry: str) -> None:
        ts = datetime.now().isoformat()
        self._tbl.add(
            [
                {
                    "key": f"history_{ts}",
                    "content": entry.rstrip(),
                    "type": "history",
                    "updated_at": ts,
                }
            ]
        )
        self._embed_and_store(entry.rstrip(), "history")

    def _embed_and_store(self, content: str, type_: str) -> None:
        if not self._embed_fn or not self._vec_tbl or not content.strip():
            return
        try:
            if type_ == "long_term":
                self._vec_tbl.delete("type = 'long_term'")
            vec = self._embed_fn.compute_source_embeddings([content])[0]
            self._vec_tbl.add([{"content": content, "type": type_, "vector": vec}])
        except Exception as e:
            logger.warning("Embedding store failed: {}", e)

    def search_memory(self, query: str, limit: int = 5) -> list[str]:
        if self._embed_fn and self._vec_tbl:
            try:
                vec = self._embed_fn.compute_query_embeddings(query)[0]
                rows = self._vec_tbl.search(vec).limit(limit).to_list()
                return [r["content"] for r in rows if r.get("content")]
            except Exception as e:
                logger.warning("Semantic search failed: {}", e)
        return self._fallback_text_search(query, limit=limit)

    def append_experience(
        self,
        task: str,
        outcome: str,
        lessons: str,
        quality: int = 3,
        category: str = "general",
        keywords: str = "",
        reasoning_trace: str = "",
    ) -> None:
        ts = datetime.now().isoformat()
        content = f"[Task] {task}\n[Outcome] {outcome}\n[Category] {category}\n[Quality] {quality}\n[Uses] 0\n[Successes] 0\n[Lessons] {lessons}"
        if keywords:
            content += f"\n[Keywords] {keywords}"
        if reasoning_trace:
            content += f"\n[Trace] {reasoning_trace}"
        self._tbl.add(
            [
                {
                    "key": f"experience_{ts}",
                    "content": content,
                    "type": "experience",
                    "updated_at": ts,
                }
            ]
        )
        self._embed_and_store(content, "experience")

    def _confidence(self, content: str) -> float:
        uses = self._parse_int_field(content, "Uses")
        successes = self._parse_int_field(content, "Successes")
        if uses < 2:
            return 1.0
        return successes / uses

    def search_experience(self, query: str, limit: int = 3) -> list[str]:
        candidates: list[dict] = []
        fetch = limit * 5
        if self._embed_fn and self._vec_tbl:
            try:
                vec = self._embed_fn.compute_query_embeddings(query)[0]
                candidates = (
                    self._vec_tbl.search(vec).where("type = 'experience'").limit(fetch).to_list()
                )
            except Exception as e:
                logger.warning("Experience search failed: {}", e)
        if not candidates:
            try:
                rows = self._tbl.search().where("type = 'experience'").limit(100).to_list()
                keywords = {w.lower() for w in query.split() if len(w) >= 2}
                if keywords:
                    candidates = [
                        r
                        for r in rows
                        if sum(1 for kw in keywords if kw in (r.get("content") or "").lower()) > 0
                    ]
                else:
                    candidates = rows
            except Exception as e:
                logger.warning("Fallback experience search failed: {}", e)
        now = datetime.now()
        positive: list[tuple[float, str]] = []
        warnings: list[tuple[float, str]] = []
        for r in candidates:
            content = r.get("content") or ""
            if "[Deprecated]" in content:
                continue
            quality = self._parse_quality(content)
            days_old = self._days_since(r.get("updated_at", ""), now)
            decay = exp(-0.02 * days_old)
            conf = self._confidence(content)
            score = quality * decay * conf
            outcome = self._parse_field(content, "Outcome")
            if outcome == "failed":
                warnings.append((score, content))
            else:
                positive.append((score, content))
        positive.sort(key=lambda x: x[0], reverse=True)
        warnings.sort(key=lambda x: x[0], reverse=True)

        results: list[str] = []
        seen_categories: dict[str, str] = {}
        for _, content in positive:
            if len(results) >= limit - 1:
                break
            cat = self._parse_field(content, "Category") or "general"
            outcome = self._parse_field(content, "Outcome")
            prev_outcome = seen_categories.get(cat)
            if prev_outcome and prev_outcome != outcome:
                content = f"⚡ CONFLICTING experience (category '{cat}' has both {prev_outcome} and {outcome}):\n{content}"
            seen_categories.setdefault(cat, outcome)
            results.append(content)

        if warnings:
            results.append(f"⚠️ WARNING from past failure:\n{warnings[0][1]}")
        return results[:limit]

    @staticmethod
    def _parse_int_field(content: str, field: str, default: int = 0) -> int:
        for line in content.split("\n"):
            if line.startswith(f"[{field}]"):
                try:
                    return int(line.split("]", 1)[1].strip())
                except (ValueError, IndexError):
                    pass
        return default

    @staticmethod
    def _parse_quality(content: str) -> int:
        return MemoryStore._parse_int_field(content, "Quality", 3)

    @staticmethod
    def _set_field(content: str, field: str, value: str) -> str:
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line.startswith(f"[{field}]"):
                lines[i] = f"[{field}] {value}"
                return "\n".join(lines)
        lines.append(f"[{field}] {value}")
        return "\n".join(lines)

    @staticmethod
    def _parse_field(content: str, field: str) -> str:
        for line in content.split("\n"):
            if line.startswith(f"[{field}]"):
                return line.split("]", 1)[1].strip()
        return ""

    @staticmethod
    def _replace_field(content: str, field: str, value: str) -> str:
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line.startswith(f"[{field}]"):
                lines[i] = f"[{field}] {value}"
                return "\n".join(lines)
        return content

    @staticmethod
    def _days_since(ts: str, now: datetime) -> float:
        if not ts:
            return 30.0
        try:
            dt = datetime.fromisoformat(ts)
            return max(0.0, (now - dt).total_seconds() / 86400)
        except (ValueError, TypeError):
            return 30.0

    def _update_experience_row(self, r: dict, new_content: str) -> None:
        if key := r.get("key"):
            self._tbl.delete(f"key = '{key}'")
            self._tbl.add(
                [
                    {
                        "key": key,
                        "content": new_content,
                        "type": "experience",
                        "updated_at": r.get("updated_at", ""),
                    }
                ]
            )

    def _match_experience_rows(self, task_desc: str, threshold: float) -> list[tuple[dict, str]]:
        rows = self._tbl.search().where("type = 'experience'").limit(100).to_list()
        keywords = {w.lower() for w in task_desc.split() if len(w) >= 2}
        if not keywords:
            return []
        results = []
        for r in rows:
            content = r.get("content") or ""
            if "[Deprecated]" in content:
                continue
            hits = sum(1 for kw in keywords if kw in content.lower())
            if hits >= len(keywords) * threshold:
                results.append((r, content))
        return results

    def deprecate_similar(self, task_desc: str) -> int:
        try:
            count = 0
            for r, content in self._match_experience_rows(task_desc, threshold=0.5):
                self._update_experience_row(r, f"[Deprecated] {content}")
                count += 1
            if count:
                logger.info("Deprecated {} experience(s) similar to: {}", count, task_desc[:60])
            return count
        except Exception as e:
            logger.warning("Experience deprecation failed: {}", e)
            return 0

    def boost_experience(self, task_desc: str, delta: int = 1) -> int:
        try:
            count = 0
            for r, content in self._match_experience_rows(task_desc, threshold=0.4):
                old_q = self._parse_quality(content)
                new_q = max(1, min(5, old_q + delta))
                if new_q == old_q:
                    continue
                self._update_experience_row(r, self._replace_field(content, "Quality", str(new_q)))
                count += 1
            if count:
                logger.info(
                    "Boosted {} experience(s) by {:+d} for: {}", count, delta, task_desc[:60]
                )
            return count
        except Exception as e:
            logger.warning("Experience boost failed: {}", e)
            return 0

    def record_reuse(self, task_desc: str, success: bool) -> int:
        try:
            count = 0
            for r, content in self._match_experience_rows(task_desc, threshold=0.4):
                uses = self._parse_int_field(content, "Uses") + 1
                successes = self._parse_int_field(content, "Successes") + (1 if success else 0)
                updated = self._set_field(content, "Uses", str(uses))
                updated = self._set_field(updated, "Successes", str(successes))
                if uses >= 3:
                    conf = successes / uses
                    current_q = self._parse_quality(updated)
                    if conf >= 0.8:
                        new_q = min(5, current_q + 1)
                    elif conf < 0.4:
                        new_q = max(1, current_q - 1)
                    else:
                        new_q = current_q
                    updated = self._set_field(updated, "Quality", str(new_q))
                self._update_experience_row(r, updated)
                count += 1
            if count:
                logger.info(
                    "Recorded reuse ({}) for {} experience(s): {}",
                    "+" if success else "-",
                    count,
                    task_desc[:60],
                )
            return count
        except Exception as e:
            logger.warning("Experience reuse recording failed: {}", e)
            return 0

    def cleanup_stale(self, max_deprecated_days: int = 30, max_low_quality_days: int = 90) -> int:
        try:
            rows = self._tbl.search().where("type = 'experience'").limit(500).to_list()
            now = datetime.now()
            removed = 0
            for r in rows:
                content = r.get("content") or ""
                days_old = self._days_since(r.get("updated_at", ""), now)
                should_remove = ("[Deprecated]" in content and days_old > max_deprecated_days) or (
                    self._parse_quality(content) <= 1 and days_old > max_low_quality_days
                )
                if should_remove and (key := r.get("key")):
                    self._tbl.delete(f"key = '{key}'")
                    removed += 1
            if removed:
                logger.info("Cleaned up {} stale experience(s)", removed)
            return removed
        except Exception as e:
            logger.warning("Experience cleanup failed: {}", e)
            return 0

    def get_merge_candidates(self, min_count: int = 5) -> list[list[str]]:
        try:
            rows = self._tbl.search().where("type = 'experience'").limit(200).to_list()
            active = [r for r in rows if "[Deprecated]" not in (r.get("content") or "")]
            if len(active) < min_count:
                return []
            groups: dict[str, list[str]] = {}
            for r in active:
                content = r.get("content") or ""
                cat = next(
                    (
                        line.split("]", 1)[1].strip() or "general"
                        for line in content.split("\n")
                        if line.startswith("[Category]")
                    ),
                    "general",
                )
                groups.setdefault(cat, []).append(content)
            return [entries for entries in groups.values() if len(entries) >= 3]
        except Exception as e:
            logger.warning("Merge candidate search failed: {}", e)
            return []

    def replace_merged(self, old_entries: list[str], merged_content: str) -> None:
        try:
            rows = self._tbl.search().where("type = 'experience'").limit(200).to_list()
            content_to_key = {r.get("content"): r.get("key") for r in rows}
            for entry in old_entries:
                if key := content_to_key.get(entry):
                    self._tbl.delete(f"key = '{key}'")
            ts = datetime.now().isoformat()
            self._tbl.add(
                [
                    {
                        "key": f"experience_merged_{ts}",
                        "content": merged_content,
                        "type": "experience",
                        "updated_at": ts,
                    }
                ]
            )
            self._embed_and_store(merged_content, "experience")
            logger.info("Merged {} experiences into 1", len(old_entries))
        except Exception as e:
            logger.warning("Experience merge failed: {}", e)

    def _fallback_text_search(
        self, query: str, type_filter: str | None = None, limit: int = 5
    ) -> list[str]:
        try:
            where = f"type = '{type_filter}'" if type_filter else "type != '_init_'"
            if not (rows := self._tbl.search().where(where).limit(100).to_list()):
                return []
            keywords = {w.lower() for w in query.split() if len(w) >= 2}
            if not keywords:
                return [r["content"] for r in rows[:limit] if r.get("content")]
            scored = sorted(
                (
                    (hits, r["content"])
                    for r in rows
                    if (hits := sum(1 for kw in keywords if kw in (r.get("content") or "").lower()))
                    > 0
                ),
                key=lambda x: x[0],
                reverse=True,
            )
            return [s[1] for s in scored[:limit]]
        except Exception as e:
            logger.warning("Fallback text search failed: {}", e)
            return []

    def get_memory_context(self) -> str:
        long_term = self.read_long_term()
        return f"## Long-term Memory\n{long_term}" if long_term else ""
