"""Memory system — LanceDB backend with columnar experience schema."""

from __future__ import annotations

import os
import threading
from collections.abc import Sized
from datetime import datetime
from math import exp, log
from pathlib import Path
from typing import Any

from loguru import logger

from bao.utils.db import ensure_table, get_db

# Schema with columnar experience fields + categorized long-term memory
_SAMPLE = [
    {
        "key": "_init_",
        "content": "",
        "type": "long_term",
        "category": "",
        "quality": 0,
        "uses": 0,
        "successes": 0,
        "outcome": "",
        "deprecated": False,
        "updated_at": "",
    }
]

_ENV_KEY = "BAO_EMBEDDING_API_KEY"
_ENV_BASE = "BAO_EMBEDDING_BASE_URL"

# Quality -> retention period (days). Higher quality decays slower.
_RETENTION_DAYS = {5: 365, 4: 180, 3: 90, 2: 30, 1: 14}

# Long-term memory categories
MEMORY_CATEGORIES = ("preference", "personal", "project", "general")


class MemoryStore:
    def __init__(self, workspace: Path, embedding_config: Any | None = None):
        self._store_lock = threading.RLock()
        self._db = get_db(workspace)
        self._tbl = self._ensure_migrated_table()
        self._embed_fn = None
        self._vec_tbl = None
        if embedding_config and getattr(embedding_config, "enabled", False):
            self._init_embedding(embedding_config)
        self._migrate_legacy(workspace)

    def _ensure_migrated_table(self):
        """Ensure memory table exists with current schema, migrating if needed."""
        try:
            tbl = self._db.open_table("memory")
            probe = tbl.search().limit(1).to_list()
            if probe and "quality" not in probe[0]:
                return self._migrate_schema(tbl)
            return tbl
        except Exception:
            return self._db.create_table("memory", data=_SAMPLE)

    def _migrate_schema(self, old_tbl):
        """Migrate from text-based to columnar schema."""
        try:
            rows = old_tbl.search().limit(10000).to_list()
            migrated = []
            for r in rows:
                new_row = {
                    "key": r.get("key", ""),
                    "content": r.get("content", ""),
                    "type": r.get("type", ""),
                    "updated_at": r.get("updated_at", ""),
                    "category": "",
                    "quality": 0,
                    "uses": 0,
                    "successes": 0,
                    "outcome": "",
                    "deprecated": False,
                }
                # Ensure long_term rows get proper category and key
                if r.get("type") == "long_term":
                    new_row["category"] = "general"
                    if new_row["key"] == "long_term":
                        new_row["key"] = "long_term_general"
                if r.get("type") == "experience":
                    content = r.get("content", "")
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
                migrated.append(new_row)
            if not migrated:
                migrated = list(_SAMPLE)
            # Clean up residual temp table from previous failed migration
            try:
                self._db.drop_table("memory_migrated")
            except Exception:
                pass
            # Create new table first, then drop old — avoids data loss if create fails
            self._db.create_table("memory_migrated", data=migrated)
            self._db.drop_table("memory")
            # LanceDB has no rename; recreate with correct name
            tbl = self._db.create_table("memory", data=migrated)
            self._db.drop_table("memory_migrated")
            # Drop stale vectors so _backfill_embeddings rebuilds with new content format
            try:
                self._db.drop_table("memory_vectors")
            except Exception:
                pass
            logger.info("Migrated memory table schema: {} rows", len(migrated))
            return tbl
        except Exception as e:
            logger.error("Schema migration failed: {}", e)
            return old_tbl

    def _init_embedding(self, cfg: Any) -> None:
        try:
            from lancedb.embeddings import get_registry

            registry = get_registry()
            backend, kwargs = self._resolve_embedding_backend(registry, cfg)
            self._embed_fn = registry.get(backend).create(**kwargs)
            # Probe actual dim with a test embedding (some backends report wrong ndims)
            probe = self._embed_fn.compute_source_embeddings(["dim probe"])
            first = probe[0] if probe else None
            ndim = len(first) if isinstance(first, Sized) else 0
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
            existing = self._tbl.search().where("type = 'long_term'").limit(1).to_list()
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

    def _make_row(self, *, key: str, content: str, type_: str, **extra) -> dict[str, Any]:
        """Build a row with all required columns, filling defaults."""
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
        }
        row.update(extra)
        return row

    # ── Long-term memory (categorized) ──

    def read_long_term(self, category: str | None = None) -> str:
        """Read long-term memory. If category given, read that category only."""
        with self._store_lock:
            try:
                if category:
                    rows = (
                        self._tbl.search()
                        .where(f"type = 'long_term' AND category = '{category}'")
                        .limit(1)
                        .to_list()
                    )
                else:
                    rows = self._tbl.search().where("type = 'long_term'").limit(20).to_list()
                if not rows:
                    return ""
                if category:
                    return rows[0].get("content", "")
                parts = []
                for r in rows:
                    cat = r.get("category") or "general"
                    content = r.get("content", "").strip()
                    if content:
                        parts.append(f"[{cat}] {content}")
                return "\n".join(parts)
            except Exception:
                return ""

    def write_long_term(self, content: str, category: str = "general") -> None:
        """Write long-term memory for a specific category."""
        if category not in MEMORY_CATEGORIES:
            category = "general"
        with self._store_lock:
            self._tbl.delete(f"type = 'long_term' AND category = '{category}'")
            self._tbl.add(
                [
                    self._make_row(
                        key=f"long_term_{category}",
                        content=content,
                        type_="long_term",
                        category=category,
                    )
                ]
            )
        self._embed_long_term_aggregate()

    def write_categorized_memory(self, updates: dict[str, str]) -> None:
        """Write multiple memory categories at once."""
        with self._store_lock:
            for cat, content in updates.items():
                if cat not in MEMORY_CATEGORIES:
                    continue
                if content and content.strip():
                    self._tbl.delete(f"type = 'long_term' AND category = '{cat}'")
                    self._tbl.add(
                        [
                            self._make_row(
                                key=f"long_term_{cat}",
                                content=content.strip(),
                                type_="long_term",
                                category=cat,
                            )
                        ]
                    )
        self._embed_long_term_aggregate()

    def append_history(self, entry: str) -> None:
        cleaned = entry.rstrip()
        with self._store_lock:
            ts = datetime.now().isoformat()
            self._tbl.add(
                [
                    self._make_row(
                        key=f"history_{ts}",
                        content=cleaned,
                        type_="history",
                        updated_at=ts,
                    )
                ]
            )
        self._embed_and_store(cleaned, "history")

    def _embed_long_term_aggregate(self) -> None:
        """Rebuild long_term vector from all categories combined."""
        aggregated = self.read_long_term()  # all categories
        if aggregated:
            self._embed_and_store(aggregated, "long_term")

    def _embed_and_store(self, content: str, type_: str) -> None:
        embed_fn = self._embed_fn
        if not embed_fn or not self._vec_tbl or not content.strip():
            return
        try:
            vec = embed_fn.compute_source_embeddings([content])[0]
            with self._store_lock:
                if not self._vec_tbl:
                    return
                if type_ == "long_term":
                    self._vec_tbl.delete("type = 'long_term'")
                self._vec_tbl.add([{"content": content, "type": type_, "vector": vec}])
        except Exception as e:
            logger.warning("Embedding store failed: {}", e)

    def search_memory(self, query: str, limit: int = 5) -> list[str]:
        embed_fn = self._embed_fn
        if embed_fn and self._vec_tbl:
            try:
                vec = embed_fn.compute_query_embeddings(query)[0]
                with self._store_lock:
                    if not self._vec_tbl:
                        return self._fallback_text_search(query, limit=limit, exclude_types=["experience", "long_term"])
                    rows = (
                        self._vec_tbl.search(vec)
                        .where("type NOT IN ('experience', 'long_term')")
                        .limit(limit)
                        .to_list()
                    )
                    return [r["content"] for r in rows if r.get("content")]
            except Exception as e:
                logger.warning("Semantic search failed: {}", e)
        return self._fallback_text_search(query, limit=limit, exclude_types=["experience", "long_term"])

    # ── Experience (columnar) ──
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
        with self._store_lock:
            ts = datetime.now().isoformat()
            parts = [f"Task: {task}", f"Lessons: {lessons}"]
            if keywords:
                parts.append(f"Keywords: {keywords}")
            if reasoning_trace:
                parts.append(f"Trace: {reasoning_trace}")
            content = "\n".join(parts)
            self._tbl.add(
                [
                    self._make_row(
                        key=f"experience_{ts}",
                        content=content,
                        type_="experience",
                        category=category,
                        quality=quality,
                        outcome=outcome,
                        updated_at=ts,
                    )
                ]
            )
        self._embed_and_store(content, "experience")

    def _confidence(self, row: dict[str, Any]) -> float:
        uses = row.get("uses", 0)
        successes = row.get("successes", 0)
        return (successes + 1) / (uses + 2)  # Laplace smoothing

    def search_experience(self, query: str, limit: int = 3) -> list[str]:
        with self._store_lock:
            candidates = self._fetch_experience_candidates(query, limit * 5)
            now = datetime.now()
            positive: list[tuple[float, str, str, str]] = []
            warnings: list[tuple[float, str, str]] = []
            for r in candidates:
                if "quality" not in r and "outcome" not in r and "updated_at" not in r:
                    continue
                if r.get("deprecated"):
                    continue
                quality = r.get("quality", 3)
                days_old = self._days_since(r.get("updated_at", ""), now)
                decay = exp(-days_old / _RETENTION_DAYS.get(quality, 90))
                conf = self._confidence(r)
                score = quality * decay * conf
                content = r.get("content") or ""
                outcome = r.get("outcome", "")
                if outcome == "failed":
                    warnings.append((score, content, r.get("category") or "general"))
                else:
                    positive.append(
                        (score, content, r.get("category") or "general", outcome or "success")
                    )
            positive.sort(key=lambda x: x[0], reverse=True)
            warnings.sort(key=lambda x: x[0], reverse=True)
            results: list[str] = []
            seen_categories: dict[str, str] = {}
            for _, content, cat, outcome_str in positive:
                if len(results) >= limit - 1:
                    break
                prev = seen_categories.get(cat)
                if prev and prev != outcome_str:
                    content = f"\u26a1 CONFLICTING experience (category '{cat}'):\n{content}"
                seen_categories.setdefault(cat, outcome_str)
                results.append(content)
            if warnings:
                results.append(f"\u26a0\ufe0f WARNING from past failure:\n{warnings[0][1]}")
            return results[:limit]

    def _fetch_experience_candidates(self, query: str, fetch: int) -> list[dict[str, Any]]:
        """Fetch experience candidates via vector or BM25 fallback."""
        if self._embed_fn and self._vec_tbl:
            try:
                vec = self._embed_fn.compute_query_embeddings(query)[0]
                vec_rows = (
                    self._vec_tbl.search(vec).where("type = 'experience'").limit(fetch).to_list()
                )
                if vec_rows:
                    if enriched := self._enrich_vector_results(vec_rows):
                        return enriched
            except Exception as e:
                logger.warning("Experience search failed: {}", e)
        try:
            rows = self._tbl.search().where("type = 'experience'").limit(100).to_list()
            ranked = self._bm25_rank(query, rows)
            return [r for _, r in ranked] if ranked else rows
        except Exception as e:
            logger.warning("Fallback experience search failed: {}", e)
            return []

    def _enrich_vector_results(self, vec_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Cross-reference vector results with main table to get columnar metadata."""
        try:
            main_rows = self._tbl.search().where("type = 'experience'").limit(500).to_list()
            content_map: dict[str, dict[str, Any]] = {}
            for r in main_rows:
                c = r.get("content", "")
                if c:
                    content_map[c] = r
            enriched = []
            for vr in vec_rows:
                vc = vr.get("content", "")
                if vc and vc in content_map:
                    enriched.append(content_map[vc])
            return enriched
        except Exception:
            return []

    @staticmethod
    def _extract_field(content: str, prefix: str) -> str:
        """Extract 'Value' from 'Prefix: Value' line in content."""
        for line in content.split("\n"):
            if line.startswith(f"{prefix}:"):
                return line.split(":", 1)[1].strip()
        return ""

    # ── Migration helpers (parse old [Field] format) ──
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

    @staticmethod
    def _days_since(ts: str, now: datetime) -> float:
        if not ts:
            return 30.0
        try:
            return max(0.0, (now - datetime.fromisoformat(ts)).total_seconds() / 86400)
        except (ValueError, TypeError):
            return 30.0

    # ── Experience mutation helpers (columnar) ──
    def _update_experience(self, r: dict[str, Any], **updates) -> None:
        """Delete old row and re-insert with updated columns."""
        if key := r.get("key"):
            self._tbl.delete(f"key = '{key}'")
            row = self._make_row(
                key=key,
                content=r.get("content", ""),
                type_="experience",
                category=r.get("category", ""),
                quality=r.get("quality", 3),
                uses=r.get("uses", 0),
                successes=r.get("successes", 0),
                outcome=r.get("outcome", ""),
                deprecated=r.get("deprecated", False),
                updated_at=datetime.now().isoformat(),
            )
            row.update(updates)
            self._tbl.add([row])

    def _match_experience_rows(self, task_desc: str, threshold: float) -> list[dict[str, Any]]:
        """Find experience rows matching task description by keyword overlap."""
        rows = self._tbl.search().where("type = 'experience'").limit(100).to_list()
        keywords = {w.lower() for w in task_desc.split() if len(w) >= 2}
        if not keywords:
            return []
        results = []
        for r in rows:
            if r.get("deprecated"):
                continue
            content = (r.get("content") or "").lower()
            hits = sum(1 for kw in keywords if kw in content)
            if hits >= len(keywords) * threshold:
                results.append(r)
        return results

    def deprecate_similar(self, task_desc: str) -> int:
        with self._store_lock:
            try:
                count = 0
                for r in self._match_experience_rows(task_desc, threshold=0.5):
                    self._update_experience(r, deprecated=True)
                    count += 1
                if count:
                    logger.info("Deprecated {} experience(s) similar to: {}", count, task_desc[:60])
                return count
            except Exception as e:
                logger.warning("Experience deprecation failed: {}", e)
                return 0

    def boost_experience(self, task_desc: str, delta: int = 1) -> int:
        with self._store_lock:
            try:
                count = 0
                for r in self._match_experience_rows(task_desc, threshold=0.4):
                    old_q = r.get("quality", 3)
                    new_q = max(1, min(5, old_q + delta))
                    if new_q != old_q:
                        self._update_experience(r, quality=new_q)
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
        with self._store_lock:
            try:
                count = 0
                for r in self._match_experience_rows(task_desc, threshold=0.4):
                    new_uses = r.get("uses", 0) + 1
                    new_successes = r.get("successes", 0) + (1 if success else 0)
                    updates: dict[str, Any] = {"uses": new_uses, "successes": new_successes}
                    if new_uses >= 3:
                        conf = new_successes / new_uses
                        cur_q = r.get("quality", 3)
                        if conf >= 0.8:
                            updates["quality"] = min(5, cur_q + 1)
                        elif conf < 0.4:
                            updates["quality"] = max(1, cur_q - 1)
                    self._update_experience(r, **updates)
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
        with self._store_lock:
            try:
                rows = self._tbl.search().where("type = 'experience'").limit(500).to_list()
                now = datetime.now()
                removed = 0
                for r in rows:
                    days_old = self._days_since(r.get("updated_at", ""), now)
                    is_dep = r.get("deprecated", False)
                    quality = r.get("quality", 3)
                    uses = r.get("uses", 0)
                    if quality >= 5 and uses >= 3 and not is_dep:
                        continue
                    should_remove = (is_dep and days_old > max_deprecated_days) or (
                        quality <= 1 and days_old > max_low_quality_days
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
        with self._store_lock:
            try:
                rows = self._tbl.search().where("type = 'experience'").limit(200).to_list()
                active = [r for r in rows if not r.get("deprecated")]
                if len(active) < min_count:
                    return []
                groups: dict[str, list[str]] = {}
                for r in active:
                    cat = r.get("category") or "general"
                    groups.setdefault(cat, []).append(r.get("content") or "")
                return [entries for entries in groups.values() if len(entries) >= 3]
            except Exception as e:
                logger.warning("Merge candidate search failed: {}", e)
                return []

    def replace_merged(
        self,
        old_entries: list[str],
        merged_content: str,
        *,
        category: str = "general",
        quality: int = 4,
    ) -> None:
        with self._store_lock:
            try:
                rows = self._tbl.search().where("type = 'experience'").limit(200).to_list()
                content_to_key = {r.get("content"): r.get("key") for r in rows}
                for entry in old_entries:
                    if key := content_to_key.get(entry):
                        self._tbl.delete(f"key = '{key}'")
                ts = datetime.now().isoformat()
                self._tbl.add(
                    [
                        self._make_row(
                            key=f"experience_merged_{ts}",
                            content=merged_content,
                            type_="experience",
                            category=category,
                            quality=quality,
                            updated_at=ts,
                        )
                    ]
                )
                logger.info("Merged {} experiences into 1", len(old_entries))
            except Exception as e:
                logger.warning("Experience merge failed: {}", e)
                return
        self._embed_and_store(merged_content, "experience")

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Split text into lowercase tokens, stripping punctuation and filtering short ones."""
        return [
            w
            for raw in text.split()
            if len(raw) >= 2
            for w in [raw.lower().strip(".,;:!?()[]{}\"'`~")]
            if len(w) >= 2
        ]

    @staticmethod
    def _bm25_rank(
        query: str, docs: list[dict[str, Any]], *, k1: float = 1.2, b: float = 0.75
    ) -> list[tuple[float, dict[str, Any]]]:
        """Rank documents by BM25 score. Returns (score, row) pairs sorted desc."""
        query_terms = MemoryStore._tokenize(query)
        if not query_terms or not docs:
            return []
        doc_tokens = [MemoryStore._tokenize(d.get("content") or "") for d in docs]
        total_len = sum(len(t) for t in doc_tokens)
        avgdl = total_len / len(doc_tokens) if doc_tokens else 1.0
        n_docs = len(docs)
        df: dict[str, int] = {}
        for qt in query_terms:
            df[qt] = sum(1 for tokens in doc_tokens if qt in tokens)
        scored: list[tuple[float, dict[str, Any]]] = []
        for i, tokens in enumerate(doc_tokens):
            if not tokens:
                continue
            dl = len(tokens)
            tf_map: dict[str, int] = {}
            for t in tokens:
                tf_map[t] = tf_map.get(t, 0) + 1
            score = 0.0
            for qt in query_terms:
                tf = tf_map.get(qt, 0)
                if tf == 0:
                    continue
                n_qt = df.get(qt, 0)
                idf = log((n_docs - n_qt + 0.5) / (n_qt + 0.5) + 1.0)
                score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
            if score > 0:
                scored.append((score, docs[i]))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def _fallback_text_search(
        self, query: str, type_filter: str | None = None, limit: int = 5,
        exclude_types: list[str] | None = None,
    ) -> list[str]:
        with self._store_lock:
            try:
                if type_filter:
                    where = f"type = '{type_filter}'"
                elif exclude_types:
                    quoted = ", ".join(f"'{t}'" for t in exclude_types)
                    where = f"type NOT IN ({quoted})"
                else:
                    where = "type != '_init_'"
                if not (rows := self._tbl.search().where(where).limit(100).to_list()):
                    return []
                ranked = self._bm25_rank(query, rows)
                if ranked:
                    return [r["content"] for _, r in ranked[:limit] if r.get("content")]
                return [r["content"] for r in rows[:limit] if r.get("content")]
            except Exception as e:
                logger.warning("Fallback text search failed: {}", e)
                return []

    def get_memory_context(self) -> str:
        long_term = self.read_long_term()
        if not long_term:
            return ""
        return f"## Long-term Memory\n{long_term}"

    # ── Explicit memory operations (for tools) ──

    def remember(self, content: str, category: str = "general") -> str:
        """Explicitly store a fact into long-term memory."""
        if category not in MEMORY_CATEGORIES:
            category = "general"
        with self._store_lock:
            rows = (
                self._tbl.search()
                .where(f"type = 'long_term' AND category = '{category}'")
                .limit(1)
                .to_list()
            )
            existing = rows[0].get("content", "") if rows else ""
            updated = f"{existing}\n{content}" if existing else content
            self._tbl.delete(f"type = 'long_term' AND category = '{category}'")
            self._tbl.add(
                [
                    self._make_row(
                        key=f"long_term_{category}",
                        content=updated,
                        type_="long_term",
                        category=category,
                    )
                ]
            )
        self._embed_long_term_aggregate()
        return f"Remembered in [{category}]: {content[:80]}"

    def forget(self, query: str) -> str:
        """Remove memory entries matching query."""
        removed = 0
        with self._store_lock:
            try:
                rows = self._tbl.search().where("type = 'long_term'").limit(50).to_list()
                for r in rows:
                    c = (r.get("content") or "").lower()
                    if query.lower() in c and (key := r.get("key")):
                        self._tbl.delete(f"key = '{key}'")
                        removed += 1
            except Exception as e:
                logger.warning("Forget failed: {}", e)
        if removed:
            self._embed_long_term_aggregate()
        return f"Removed {removed} memory entries matching '{query[:40]}'."

    def update_memory(self, category: str, content: str) -> str:
        """Replace entire content of a memory category."""
        if category not in MEMORY_CATEGORIES:
            return f"Invalid category. Use one of: {', '.join(MEMORY_CATEGORIES)}"
        with self._store_lock:
            self._tbl.delete(f"type = 'long_term' AND category = '{category}'")
            self._tbl.add(
                [
                    self._make_row(
                        key=f"long_term_{category}",
                        content=content,
                        type_="long_term",
                        category=category,
                    )
                ]
            )
        self._embed_long_term_aggregate()
        return f"Updated [{category}] memory."
