"""Memory system — LanceDB backend with columnar experience schema."""

from __future__ import annotations

import threading
import time
from collections.abc import Sized
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime
from math import exp, log
from pathlib import Path
from typing import Any, Callable

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
        "last_hit_at": "",
        "hit_count": 0,
    }
]

_ENV_KEY = "BAO_EMBEDDING_API_KEY"
_ENV_BASE = "BAO_EMBEDDING_BASE_URL"

_DEFAULT_EMBED_TIMEOUT_S = 15
_DEFAULT_EMBED_RETRY_ATTEMPTS = 2
_DEFAULT_EMBED_RETRY_BACKOFF_MS = 200
_QUERY_EMBED_CACHE_TTL_S = 120.0
_QUERY_EMBED_CACHE_MAX = 256
_BACKFILL_SCAN_LIMIT = 20000
_MIGRATION_CHUNK_SIZE = 1000

# Quality -> retention period (days). Higher quality decays slower.
_RETENTION_DAYS = {5: 365, 4: 180, 3: 90, 2: 30, 1: 14}

# Long-term memory categories
MEMORY_CATEGORIES = ("preference", "personal", "project", "general")

MEMORY_CATEGORY_CAPS = {
    "preference": 400,
    "personal": 300,
    "project": 500,
    "general": 300,
}

_LOW_INFORMATION_QUERIES = frozenset(
    {
        "ok",
        "okay",
        "thanks",
        "thankyou",
        "thx",
        "gotit",
        "roger",
        "sure",
        "yes",
        "no",
        "hi",
        "hello",
        "收到",
        "知道了",
        "明白了",
        "好的",
        "好哦",
        "行",
        "可以",
        "继续",
        "谢谢",
        "多谢",
        "辛苦了",
        "嗯",
        "嗯嗯",
        "哦",
        "哦哦",
        "嗨",
        "你好",
        "好",
    }
)

# Category importance weights for rerank scoring (higher = more important to retain)
_CATEGORY_WEIGHTS: dict[str, float] = {
    "preference": 1.0,
    "project": 0.8,
    "personal": 0.6,
    "general": 0.4,
}


class _GeminiEmbedding:
    """Thin wrapper using google-genai SDK (avoids legacy google-generativeai dependency)."""

    def __init__(self, model: str, api_key: str):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def compute_source_embeddings(self, texts: list[str]) -> list[list[float]]:
        result = self._client.models.embed_content(
            model=self._model,
            contents=[str(t) for t in texts],
            config={"task_type": "RETRIEVAL_DOCUMENT"},
        )
        return [e.values or [] for e in (result.embeddings or [])]

    def compute_query_embeddings(self, query: str) -> list[list[float]]:
        result = self._client.models.embed_content(
            model=self._model,
            contents=[query],
            config={"task_type": "RETRIEVAL_QUERY"},
        )
        return [e.values or [] for e in (result.embeddings or [])]


class MemoryStore:
    _EMBED_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="Bao-embed")
    _MEMORY_BG_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="Bao-memory-bg")

    def __init__(self, workspace: Path, embedding_config: Any | None = None):
        self._store_lock = threading.RLock()
        self._db: Any = get_db(workspace)
        self._tbl: Any = self._ensure_migrated_table()
        self._embed_fn = None
        self._vec_tbl: Any | None = None
        self._embed_timeout_s = _DEFAULT_EMBED_TIMEOUT_S
        self._embed_retry_attempts = _DEFAULT_EMBED_RETRY_ATTEMPTS
        self._embed_retry_backoff_ms = _DEFAULT_EMBED_RETRY_BACKOFF_MS
        self._query_embed_cache: dict[str, tuple[float, list[list[float]]]] = {}
        self._query_embed_cache_lock = threading.Lock()
        if embedding_config and getattr(embedding_config, "enabled", False):
            self._init_embedding(embedding_config)
        self._migrate_legacy(workspace)

    def close(self) -> None:
        with self._store_lock:
            self._vec_tbl = None
            self._embed_fn = None

    def _ensure_migrated_table(self):
        """Ensure memory table exists with current schema, migrating if needed."""
        try:
            tbl = self._db.open_table("memory")
            probe = tbl.search().limit(1).to_list()
            if probe and "quality" not in probe[0]:
                return self._migrate_schema(tbl)
            # Check for newer columns added after columnar migration
            if probe and "hit_count" not in probe[0]:
                return self._backfill_new_columns(tbl)
            return tbl
        except Exception:
            return ensure_table(self._db, "memory", list(_SAMPLE))

    def _migrate_schema(self, old_tbl):
        """Migrate from text-based to columnar schema."""
        try:
            rows = old_tbl.search().to_list()
            # Clean up residual temp table from previous failed migration
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
            for r in source_rows:
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
                    "last_hit_at": "",
                    "hit_count": 0,
                }
                if r.get("type") == "long_term":
                    new_row["category"] = "general"
                    if new_row["key"] == "long_term":
                        new_row["key"] = "long_term_general"
                if r.get("type") == "experience":
                    content = str(r.get("content", ""))
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
            # LanceDB has no rename; recreate with correct name
            tbl = self._db.create_table("memory", data=staged_rows)
            self._db.drop_table("memory_migrated")
            # Drop stale vectors so _backfill_embeddings rebuilds with new content format
            try:
                self._db.drop_table("memory_vectors")
            except Exception:
                pass
            logger.info("🔀 迁移结构 / schema migrated: {} rows", migrated_count)
            return tbl
        except Exception as e:
            logger.error("❌ 迁移失败 / schema migration failed: {}", e)
            return old_tbl

    def _backfill_new_columns(self, tbl):
        """Backfill missing columns (last_hit_at, hit_count) for existing columnar tables."""
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
            for r in source_rows:
                row = dict(r)
                row.setdefault("last_hit_at", "")
                row.setdefault("hit_count", 0)
                row.pop("_distance", None)
                row.pop("_relevance_score", None)
                row.pop("vector", None)
                batch.append(row)
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
            logger.info("🔀 补齐新列 / backfilled new columns: {} rows", patched_count)
            return tbl
        except Exception as e:
            logger.error("❌ 补齐新列失败 / backfill failed: {}", e)
            return tbl

    def _init_embedding(self, cfg: Any) -> None:
        try:
            self._embed_timeout_s = max(
                1, int(getattr(cfg, "timeout_seconds", _DEFAULT_EMBED_TIMEOUT_S))
            )
            self._embed_retry_attempts = max(
                1, int(getattr(cfg, "retry_attempts", _DEFAULT_EMBED_RETRY_ATTEMPTS))
            )
            self._embed_retry_backoff_ms = max(
                0, int(getattr(cfg, "retry_backoff_ms", _DEFAULT_EMBED_RETRY_BACKOFF_MS))
            )
            api_key = cfg.api_key.get_secret_value()
            model_lower = cfg.model.lower()
            if "gemini" in model_lower or "models/embedding" in model_lower:
                name = cfg.model if cfg.model.startswith("models/") else f"models/{cfg.model}"
                self._embed_fn = _GeminiEmbedding(model=name, api_key=api_key)
                backend = "gemini-genai"
            else:
                from lancedb.embeddings import get_registry

                registry = get_registry()
                backend, kwargs = self._resolve_embedding_backend(registry, cfg)
                self._embed_fn = registry.get(backend).create(**kwargs)
            # Probe actual dim with a test embedding (some backends report wrong ndims)
            probe = self._compute_source_embeddings(["dim probe"])
            first = probe[0] if probe else None
            ndim = len(first) if isinstance(first, Sized) else 0
            if ndim <= 0:
                raise ValueError("embedding dimension probe returned empty vector")
            self._vec_tbl = ensure_table(
                self._db,
                "memory_vectors",
                [{"key": "_init_", "content": "", "type": "long_term", "vector": [0.0] * ndim}],
            )
            if self._vector_table_needs_rebuild(expected_dim=ndim):
                self._rebuild_vector_table(ndim)
            logger.debug("Embedding enabled: {} via {} (dim={})", cfg.model, backend, ndim)
            self._backfill_embeddings()
        except Exception as e:
            logger.warning("⚠️ 向量初始化失败 / embedding init failed: {}", e)
            self._embed_fn = None
            self._vec_tbl = None

    @staticmethod
    def _run_with_timeout(timeout_s: int, fn: Callable[[], Any]) -> Any:
        fut = MemoryStore._EMBED_EXECUTOR.submit(fn)
        try:
            return fut.result(timeout=timeout_s)
        except FuturesTimeoutError as exc:
            fut.cancel()
            raise TimeoutError(f"Embedding request timed out after {timeout_s}s") from exc

    @staticmethod
    def _is_retryable_embedding_error(exc: Exception) -> bool:
        if isinstance(exc, TimeoutError | FuturesTimeoutError):
            return True
        msg = str(exc).lower()
        retry_markers = (
            "timeout",
            "timed out",
            "rate limit",
            "too many requests",
            "429",
            "503",
            "connection",
            "temporarily unavailable",
            "service unavailable",
        )
        return any(marker in msg for marker in retry_markers)

    def _call_embedding_with_retry(self, fn: Callable[[], Any], *, op: str) -> Any:
        attempts = self._embed_retry_attempts
        last_exc: Exception | None = None
        for idx in range(attempts):
            try:
                return self._run_with_timeout(self._embed_timeout_s, fn)
            except Exception as exc:
                last_exc = exc
                is_last = idx >= attempts - 1
                if is_last or not self._is_retryable_embedding_error(exc):
                    raise
                sleep_s = (self._embed_retry_backoff_ms / 1000.0) * (2**idx)
                if sleep_s > 0:
                    logger.debug("Embedding {} retry {}/{} after {}", op, idx + 1, attempts, exc)
                    time.sleep(sleep_s)
        if last_exc is not None:
            raise last_exc

    def _compute_source_embeddings(self, texts: list[str]) -> list[list[float]]:
        embed_fn = self._embed_fn
        if not embed_fn:
            return []
        assert embed_fn is not None
        return self._call_embedding_with_retry(
            lambda: embed_fn.compute_source_embeddings(texts),
            op="source",
        )

    def _ensure_query_embed_cache(self) -> None:
        if not hasattr(self, "_query_embed_cache"):
            self._query_embed_cache = {}
        if not hasattr(self, "_query_embed_cache_lock"):
            self._query_embed_cache_lock = threading.Lock()

    def _compute_query_embeddings(self, query: str) -> list[list[float]]:
        embed_fn = self._embed_fn
        if not embed_fn:
            return []
        assert embed_fn is not None
        self._ensure_query_embed_cache()
        now = time.monotonic()
        with self._query_embed_cache_lock:
            cached = self._query_embed_cache.get(query)
            if cached and cached[0] > now:
                return cached[1]
            if cached:
                self._query_embed_cache.pop(query, None)

        vectors = self._call_embedding_with_retry(
            lambda: embed_fn.compute_query_embeddings(query),
            op="query",
        )
        with self._query_embed_cache_lock:
            self._query_embed_cache[query] = (now + _QUERY_EMBED_CACHE_TTL_S, vectors)
            while len(self._query_embed_cache) > _QUERY_EMBED_CACHE_MAX:
                self._query_embed_cache.pop(next(iter(self._query_embed_cache)))
        return vectors

    @staticmethod
    def _log_background_exception(fut: Any) -> None:
        try:
            fut.result()
        except Exception as e:
            logger.debug("memory background task skipped: {}", e)

    def _schedule_hit_stats_update(self, rows: list[dict[str, Any]]) -> None:
        snapshot = [dict(r) for r in rows if r.get("key")]
        if not snapshot:
            return
        fut = self._MEMORY_BG_EXECUTOR.submit(self._update_hit_stats, snapshot)
        fut.add_done_callback(self._log_background_exception)

    def _vector_table_needs_rebuild(self, *, expected_dim: int) -> bool:
        if not self._vec_tbl:
            return False
        try:
            rows = self._vec_tbl.search().limit(3).to_list()
        except Exception:
            return True
        if not rows:
            return False
        sample = rows[0]
        if "key" not in sample:
            return True
        vec = sample.get("vector")
        current_dim = len(vec) if isinstance(vec, Sized) else 0
        if current_dim <= 0:
            return True
        return current_dim != expected_dim

    def _rebuild_vector_table(self, ndim: int) -> None:
        self._db.drop_table("memory_vectors")
        self._vec_tbl = ensure_table(
            self._db,
            "memory_vectors",
            [{"key": "_init_", "content": "", "type": "long_term", "vector": [0.0] * ndim}],
        )
        logger.info("🔁 重建向量表 / vector table rebuilt (dim={})", ndim)

    @staticmethod
    def _resolve_embedding_backend(registry: Any, cfg: Any) -> tuple[str, dict[str, Any]]:
        # LanceDB requires `$var:` references for sensitive keys, resolved via registry
        registry.set_var(_ENV_KEY, cfg.api_key.get_secret_value())
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
            with self._store_lock:
                rows = self._tbl.search().where("type != '_init_'").to_list()
            main_by_key: dict[str, dict[str, Any]] = {}
            for r in rows:
                key = r.get("key", "")
                content = r.get("content", "").strip()
                type_ = r.get("type", "")
                if key and content and type_:
                    main_by_key[key] = r
            with self._store_lock:
                vec_rows = self._vec_tbl.search().to_list()
            vec_by_key = {
                r.get("key", ""): r for r in vec_rows if r.get("key") and r.get("key") != "_init_"
            }

            count = 0
            refresh_count = 0
            for key, r in main_by_key.items():
                content = r.get("content", "")
                type_ = r.get("type", "")
                existing = vec_by_key.get(key)
                if not existing:
                    self._store_vector_for_row(key=key, content=content, type_=type_)
                    count += 1
                    continue
                if existing.get("content", "") != content or existing.get("type", "") != type_:
                    self._store_vector_for_row(key=key, content=content, type_=type_)
                    refresh_count += 1
            if count:
                logger.info("🧠 补全向量 / embeddings backfilled: {} records", count)
            if refresh_count:
                logger.info("♻️ 刷新向量 / embeddings refreshed: {} records", refresh_count)
        except Exception as e:
            logger.warning("⚠️ 向量补全失败 / embedding backfill failed: {}", e)

    def _delete_vector_by_key(self, key: str) -> None:
        if not self._vec_tbl or not key:
            return
        key_safe = key.replace("'", "''")
        with self._store_lock:
            if not self._vec_tbl:
                return
            self._vec_tbl.delete(f"key = '{key_safe}'")

    def _store_vector_for_row(self, *, key: str, content: str, type_: str) -> None:
        if not self._vec_tbl or not self._embed_fn or not key or not content.strip() or not type_:
            return
        vectors = self._compute_source_embeddings([content])
        vec = vectors[0] if vectors else None
        if not isinstance(vec, Sized) or len(vec) == 0:
            raise ValueError("embedding returned empty vector")
        with self._store_lock:
            if not self._vec_tbl:
                return
            self._delete_vector_by_key(key)
            self._vec_tbl.add([{"key": key, "content": content, "type": type_, "vector": vec}])

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
            "last_hit_at": extra.pop("last_hit_at", ""),
            "hit_count": extra.pop("hit_count", 0),
        }
        row.update(extra)
        return row

    @staticmethod
    def _normalize_memory(content: str, *, max_chars: int) -> str:
        if max_chars <= 0:
            return ""
        cleaned_lines: list[str] = []
        seen: set[str] = set()
        for line in str(content).splitlines():
            stripped = line.strip()
            if not stripped or stripped in seen:
                continue
            seen.add(stripped)
            cleaned_lines.append(stripped)
        normalized = "\n".join(cleaned_lines)
        if len(normalized) <= max_chars:
            return normalized
        if max_chars <= 1:
            return "…"
        cut = normalized.rfind("\n", 0, max_chars)
        if cut > max_chars // 2:
            return normalized[:cut].rstrip() + "…"
        return normalized[: max_chars - 1].rstrip() + "…"

    def _update_hit_stats(self, rows: list[dict[str, Any]]) -> None:
        """Increment hit_count and update last_hit_at for retrieved rows (best-effort)."""
        now = datetime.now().isoformat()
        with self._store_lock:
            for r in rows:
                key = r.get("key")
                if not key:
                    continue
                try:
                    key_safe = key.replace("'", "''")
                    # Snapshot before delete so we can restore on add failure
                    self._tbl.delete(f"key = '{key_safe}'")
                    row = self._make_row(
                        key=key,
                        content=r.get("content", ""),
                        type_=r.get("type", ""),
                        category=r.get("category", ""),
                        quality=r.get("quality", 0),
                        uses=r.get("uses", 0),
                        successes=r.get("successes", 0),
                        outcome=r.get("outcome", ""),
                        deprecated=r.get("deprecated", False),
                        updated_at=r.get("updated_at", now),
                        last_hit_at=now,
                        hit_count=r.get("hit_count", 0) + 1,
                    )
                    try:
                        self._tbl.add([row])
                    except Exception:
                        # add failed after delete — restore original row to prevent data loss
                        try:
                            self._tbl.add(
                                [
                                    self._make_row(
                                        key=key,
                                        content=r.get("content", ""),
                                        type_=r.get("type", ""),
                                        **{
                                            k: r.get(k, v)
                                            for k, v in {
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
                                ]
                            )
                        except Exception:
                            logger.warning("⚠️ hit_stats: failed to restore row key={}", key)
                except Exception as e:
                    logger.debug("hit_stats update skipped for key={}: {}", key, e)

    def _rerank_candidates(
        self,
        candidates: list[dict[str, Any]],
        *,
        limit: int,
        has_vector_score: bool = False,
    ) -> list[dict[str, Any]]:
        """Multi-factor rule-based rerank. No external model needed.

        Factors: semantic distance (if available), recency, quality/importance, reliability.
        """
        now = datetime.now()
        scored: list[tuple[float, dict[str, Any]]] = []
        for r in candidates:
            if r.get("deprecated"):
                continue
            # Factor 1: semantic (vector distance — lower is better, invert to score)
            if has_vector_score and "_distance" in r:
                # LanceDB distance is L2; typical range 0~2. Normalize to 0~1 score.
                semantic = max(0.0, 1.0 - r["_distance"] / 2.0)
            else:
                semantic = 0.5  # neutral when no vector score

            text_score_raw = r.get("_text_score", 0.0)
            if isinstance(text_score_raw, (int, float)) and text_score_raw > 0:
                text_signal = float(text_score_raw) / (1.0 + float(text_score_raw))
            else:
                text_signal = 0.0

            # Factor 2: recency (exponential decay)
            days_old = self._days_since(r.get("updated_at", ""), now)
            recency = exp(-days_old / 90)

            # Factor 3: importance (category weight + quality)
            cat = r.get("category") or "general"
            cat_weight = _CATEGORY_WEIGHTS.get(cat, 0.4)
            quality = r.get("quality", 3) / 5.0
            importance = 0.5 * cat_weight + 0.5 * quality

            # Factor 4: reliability (Laplace-smoothed success rate)
            # For non-experience rows (uses=0, successes=0), this yields 0.5 (neutral),
            # which is intentional — reliability only differentiates experience rows.
            reliability = self._confidence(r)

            score = (
                0.30 * semantic
                + 0.20 * text_signal
                + 0.20 * recency
                + 0.20 * importance
                + 0.10 * reliability
            )
            scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]

    def _enrich_for_rerank(self, vec_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Cross-reference vector results with main table to get columnar metadata for rerank."""
        try:
            keys = [str(vr.get("key", "")) for vr in vec_rows if vr.get("key")]
            with self._store_lock:
                key_map: dict[str, dict[str, Any]] = {}
                for key in keys:
                    key_safe = key.replace("'", "''")
                    rows = self._tbl.search().where(f"key = '{key_safe}'").limit(1).to_list()
                    if rows:
                        key_map[key] = rows[0]
                needs_fallback = any(not vr.get("key") for vr in vec_rows)
                main_rows = (
                    self._tbl.search().where("type != '_init_'").limit(500).to_list()
                    if needs_fallback
                    else []
                )
            content_map: dict[tuple[str, str], dict[str, Any]] = {}
            for r in main_rows:
                c = r.get("content", "")
                t = r.get("type", "")
                if c:
                    content_map[(c, t)] = r
            enriched = []
            for vr in vec_rows:
                key = vr.get("key", "")
                vc = vr.get("content", "")
                vt = vr.get("type", "")
                matched = key_map.get(key) if key else content_map.get((vc, vt))
                if matched:
                    merged = dict(matched)
                    if "_distance" in vr:
                        merged["_distance"] = vr["_distance"]
                    enriched.append(merged)
            return enriched
        except Exception:
            return vec_rows

    # ── Long-term memory (categorized) ──

    def read_long_term(self, category: str | None = None) -> str:
        """Read long-term memory. If category given, read that category only."""
        with self._store_lock:
            try:
                rows = self._read_long_term_rows_locked()
                if not rows:
                    return ""
                if category:
                    for row in rows:
                        if (row.get("category") or "general") == category:
                            return row.get("content", "")
                    return ""
                parts = []
                for r in rows:
                    cat = r.get("category") or "general"
                    content = r.get("content", "").strip()
                    if content:
                        parts.append(f"[{cat}] {content}")
                return "\n".join(parts)
            except Exception:
                return ""

    def _read_long_term_rows_locked(self) -> list[dict[str, Any]]:
        return self._tbl.search().where("type = 'long_term'").limit(20).to_list()

    def list_long_term_entries(self) -> list[dict[str, str]]:
        with self._store_lock:
            try:
                rows = self._tbl.search().where("type = 'long_term'").limit(20).to_list()
                return [
                    {
                        "key": r.get("key", ""),
                        "category": r.get("category") or "general",
                        "content": r.get("content", ""),
                    }
                    for r in rows
                    if r.get("content", "").strip()
                ]
            except Exception:
                return []

    def list_memory_categories(self) -> list[dict[str, Any]]:
        with self._store_lock:
            try:
                rows = self._read_long_term_rows_locked()
            except Exception:
                rows = []

        by_category = {
            str(row.get("category") or "general"): dict(row)
            for row in rows
            if str(row.get("category") or "general") in MEMORY_CATEGORIES
        }
        items: list[dict[str, Any]] = []
        for category in MEMORY_CATEGORIES:
            row = by_category.get(category, {})
            content = str(row.get("content", "")).strip()
            preview = content.replace("\n", " ")[:160]
            if len(content.replace("\n", " ")) > 160:
                preview += "…"
            items.append(
                {
                    "key": str(row.get("key") or f"long_term_{category}"),
                    "category": category,
                    "content": content,
                    "preview": preview,
                    "updated_at": str(row.get("updated_at", "")),
                    "char_count": len(content),
                    "line_count": len([line for line in content.splitlines() if line.strip()]),
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

    def exists_long_term_key(self, key: str) -> bool:
        if not key:
            return False
        key_safe = key.replace("'", "''")
        with self._store_lock:
            try:
                rows = (
                    self._tbl.search()
                    .where(f"type = 'long_term' AND key = '{key_safe}'")
                    .limit(1)
                    .to_list()
                )
                return bool(rows)
            except Exception:
                return False

    def delete_long_term_by_key(self, key: str) -> bool:
        if not key:
            return False
        key_safe = key.replace("'", "''")
        with self._store_lock:
            try:
                rows = (
                    self._tbl.search()
                    .where(f"type = 'long_term' AND key = '{key_safe}'")
                    .limit(1)
                    .to_list()
                )
                if not rows:
                    return False
                self._tbl.delete(f"type = 'long_term' AND key = '{key_safe}'")
                return True
            except Exception as e:
                logger.warning("⚠️ 按键删除失败 / delete by key failed: {}", e)
                return False

    def _read_long_term_content_locked(self, category: str) -> str:
        rows = self._read_long_term_rows_locked()
        for row in rows:
            if (row.get("category") or "general") == category:
                return str(row.get("content", ""))
        return ""

    def _upsert_long_term_locked(self, category: str, normalized: str) -> bool:
        current = self._read_long_term_content_locked(category)
        if current == normalized:
            return False

        self._tbl.delete(f"type = 'long_term' AND category = '{category}'")
        if normalized:
            self._tbl.add(
                [
                    self._make_row(
                        key=f"long_term_{category}",
                        content=normalized,
                        type_="long_term",
                        category=category,
                    )
                ]
            )
        return True

    def write_long_term(self, content: str, category: str = "general") -> None:
        """Write long-term memory for a specific category."""
        if category not in MEMORY_CATEGORIES:
            category = "general"
        cap = MEMORY_CATEGORY_CAPS.get(category, MEMORY_CATEGORY_CAPS["general"])
        normalized = self._normalize_memory(content, max_chars=cap)
        with self._store_lock:
            changed = self._upsert_long_term_locked(category, normalized)
        if changed:
            self._schedule_long_term_embedding()

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
        """Write multiple memory categories at once."""
        changed_any = False
        with self._store_lock:
            for cat, content in updates.items():
                if cat not in MEMORY_CATEGORIES:
                    continue
                cap = MEMORY_CATEGORY_CAPS.get(cat, MEMORY_CATEGORY_CAPS["general"])
                if content is None:
                    content_str = ""
                elif isinstance(content, str):
                    content_str = content.strip()
                elif isinstance(content, list):
                    content_str = "\n".join(
                        str(x).strip() for x in content if x is not None and str(x).strip()
                    )
                else:
                    continue

                normalized = self._normalize_memory(content_str, max_chars=cap)
                if self._upsert_long_term_locked(cat, normalized):
                    changed_any = True
        if changed_any:
            self._schedule_long_term_embedding()

    def append_history(self, entry: str) -> None:
        cleaned = entry.rstrip()
        row_key = ""
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
        self._embed_and_store(key=row_key, content=cleaned, type_="history")

    def _embed_long_term_aggregate(self) -> None:
        """Rebuild long_term vector from all categories combined."""
        aggregated = self.read_long_term()  # all categories
        if aggregated:
            self._embed_and_store(
                key="long_term_aggregate",
                content=aggregated,
                type_="long_term",
            )
        elif self._vec_tbl:
            try:
                with self._store_lock:
                    rows = self._tbl.search().where("type = 'long_term'").limit(20).to_list()
                    has_content = any(r.get("content", "").strip() for r in rows) if rows else False
                    if not has_content and self._vec_tbl:
                        self._delete_vector_by_key("long_term_aggregate")
            except Exception as e:
                logger.warning("⚠️ 长期向量清理失败 / long-term vector clear failed: {}", e)

    def embed_long_term_aggregate(self) -> None:
        self._embed_long_term_aggregate()

    def _schedule_long_term_embedding(self) -> None:
        if not self._embed_fn or not self._vec_tbl:
            return

        fut = self._MEMORY_BG_EXECUTOR.submit(self._embed_long_term_aggregate)

        def _log_if_failed(future) -> None:
            try:
                future.result()
            except Exception as e:
                logger.warning("⚠️ 长期向量异步更新失败 / async long-term embedding failed: {}", e)

        fut.add_done_callback(_log_if_failed)

    def _embed_and_store(self, *, key: str, content: str, type_: str) -> None:
        if not self._embed_fn or not self._vec_tbl or not content.strip():
            return
        try:
            self._store_vector_for_row(key=key, content=content, type_=type_)
        except Exception as e:
            logger.warning("⚠️ 向量写入失败 / embedding store failed: {}", e)

    @staticmethod
    def _candidate_identity(row: dict[str, Any]) -> tuple[str, str] | tuple[str, str, str]:
        key = str(row.get("key", "")).strip()
        if key:
            return ("key", key)
        return (
            "content",
            str(row.get("type", "")),
            str(row.get("content", "")),
        )

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
    ) -> list[dict[str, Any]]:
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
                    out: list[dict[str, Any]] = []
                    for score, row in ranked[:limit]:
                        if not row.get("content"):
                            continue
                        item = dict(row)
                        item["_text_score"] = score
                        out.append(item)
                    return out

                return [dict(r) for r in rows[:limit] if r.get("content")]
            except Exception as e:
                logger.warning("⚠️ 文本回退失败 / text fallback failed: {}", e)
                return []

    def search_memory(self, query: str, limit: int = 5) -> list[str]:
        if self.should_skip_retrieval(query):
            return []
        embed_fn = self._embed_fn
        fetch = max(limit * 3, 6)
        vec_enriched: list[dict[str, Any]] = []

        if embed_fn and self._vec_tbl:
            try:
                vectors = self._compute_query_embeddings(query)
                vec = vectors[0] if vectors else None
                if not isinstance(vec, Sized) or len(vec) == 0:
                    raise ValueError("query embedding returned empty vector")
                with self._store_lock:
                    if not self._vec_tbl:
                        vec_rows = []
                    else:
                        vec_rows = (
                            self._vec_tbl.search(vec)
                            .where("type NOT IN ('experience', 'long_term')")
                            .limit(fetch)
                            .to_list()
                        )
                if vec_rows:
                    vec_enriched = self._enrich_for_rerank(vec_rows)
            except Exception as e:
                logger.warning("⚠️ 语义检索失败 / semantic search failed: {}", e)

        text_candidates = self._fallback_text_candidates(
            query,
            limit=fetch,
            exclude_types=["experience", "long_term"],
        )

        candidates = self._merge_memory_candidates(vec_enriched, text_candidates)
        if candidates:
            reranked = self._rerank_candidates(
                candidates,
                limit=limit,
                has_vector_score=bool(vec_enriched),
            )
            if reranked:
                return [r["content"] for r in reranked if r.get("content")]

        return []

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
        row_key = ""
        with self._store_lock:
            ts = datetime.now().isoformat()
            row_key = f"experience_{ts}"
            parts = [f"Task: {task}", f"Lessons: {lessons}"]
            if keywords:
                parts.append(f"Keywords: {keywords}")
            if reasoning_trace:
                parts.append(f"Trace: {reasoning_trace}")
            content = "\n".join(parts)
            self._tbl.add(
                [
                    self._make_row(
                        key=row_key,
                        content=content,
                        type_="experience",
                        category=category,
                        quality=quality,
                        outcome=outcome,
                        updated_at=ts,
                    )
                ]
            )
        self._embed_and_store(key=row_key, content=content, type_="experience")

    def _confidence(self, row: dict[str, Any]) -> float:
        uses = row.get("uses", 0)
        successes = row.get("successes", 0)
        return (successes + 1) / (uses + 2)  # Laplace smoothing

    def search_experience(self, query: str, limit: int = 3) -> list[str]:
        """Search experiences with scoring + conflict detection + hit tracking."""
        if self.should_skip_retrieval(query):
            return []
        candidates = self._fetch_experience_candidates(query, limit * 5)
        now = datetime.now()
        positive: list[tuple[float, dict[str, Any], str, str, str]] = []
        warnings: list[tuple[float, dict[str, Any], str, str]] = []
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
                warnings.append((score, r, content, r.get("category") or "general"))
            else:
                positive.append(
                    (score, r, content, r.get("category") or "general", outcome or "success")
                )
        positive.sort(key=lambda x: x[0], reverse=True)
        warnings.sort(key=lambda x: x[0], reverse=True)
        results: list[str] = []
        hit_rows: list[dict[str, Any]] = []
        seen_categories: dict[str, str] = {}
        for _, row, content, cat, outcome_str in positive:
            if len(results) >= limit - 1:
                break
            prev = seen_categories.get(cat)
            if prev and prev != outcome_str:
                content = f"\u26a1 CONFLICTING experience (category '{cat}'):\n{content}"
            seen_categories.setdefault(cat, outcome_str)
            results.append(content)
            hit_rows.append(row)
        if warnings:
            results.append(f"\u26a0\ufe0f WARNING from past failure:\n{warnings[0][2]}")
            hit_rows.append(warnings[0][1])
        final = results[:limit]
        # Update hit stats outside the main lock (best-effort)
        if hit_rows:
            self._schedule_hit_stats_update(hit_rows)
        return final

    @staticmethod
    def _experience_preview(task: str, lessons: str) -> str:
        base = f"{task} — {lessons}" if task and lessons else (task or lessons)
        cleaned = base.replace("\n", " ").strip()
        if len(cleaned) <= 180:
            return cleaned
        return cleaned[:179].rstrip() + "…"

    def _experience_row_to_item(self, row: dict[str, Any]) -> dict[str, Any]:
        content = str(row.get("content") or "")
        task = self._extract_field(content, "Task")
        lessons = self._extract_field(content, "Lessons")
        keywords = self._extract_field(content, "Keywords")
        trace = self._extract_field(content, "Trace")
        return {
            "key": str(row.get("key") or ""),
            "task": task,
            "lessons": lessons,
            "keywords": keywords,
            "trace": trace,
            "content": content,
            "preview": self._experience_preview(task, lessons),
            "category": str(row.get("category") or "general"),
            "outcome": str(row.get("outcome") or ""),
            "quality": int(row.get("quality", 0) or 0),
            "uses": int(row.get("uses", 0) or 0),
            "successes": int(row.get("successes", 0) or 0),
            "deprecated": bool(row.get("deprecated", False)),
            "updated_at": str(row.get("updated_at", "")),
            "hit_count": int(row.get("hit_count", 0) or 0),
            "last_hit_at": str(row.get("last_hit_at", "")),
        }

    def list_experience_items(
        self,
        query: str = "",
        *,
        category: str = "",
        outcome: str = "",
        deprecated: bool | None = None,
        min_quality: int = 0,
        sort_by: str = "updated_desc",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._store_lock:
            try:
                rows = (
                    self._tbl.search()
                    .where("type = 'experience'")
                    .limit(max(limit * 2, 200))
                    .to_list()
                )
            except Exception:
                return []

        items = [self._experience_row_to_item(row) for row in rows]
        if query and not self.should_skip_retrieval(query):
            query_tokens = set(self._tokenize(query))
            if query_tokens:
                items = [
                    item
                    for item in items
                    if query_tokens
                    & set(
                        self._tokenize(
                            " ".join(
                                [
                                    str(item.get("task", "")),
                                    str(item.get("lessons", "")),
                                    str(item.get("keywords", "")),
                                    str(item.get("category", "")),
                                    str(item.get("outcome", "")),
                                ]
                            )
                        )
                    )
                ]
        if category:
            items = [item for item in items if item.get("category") == category]
        if outcome:
            items = [item for item in items if item.get("outcome") == outcome]
        if deprecated is not None:
            items = [item for item in items if bool(item.get("deprecated")) is deprecated]
        if min_quality > 0:
            items = [item for item in items if int(item.get("quality", 0)) >= min_quality]

        if sort_by == "quality_desc":
            items.sort(
                key=lambda item: (
                    int(item.get("quality", 0)),
                    int(item.get("uses", 0)),
                    str(item.get("updated_at", "")),
                ),
                reverse=True,
            )
        elif sort_by == "uses_desc":
            items.sort(
                key=lambda item: (
                    int(item.get("uses", 0)),
                    int(item.get("successes", 0)),
                    str(item.get("updated_at", "")),
                ),
                reverse=True,
            )
        else:
            items.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return items[:limit]

    def get_experience_item(self, key: str) -> dict[str, Any] | None:
        if not key:
            return None
        key_safe = key.replace("'", "''")
        with self._store_lock:
            try:
                rows = (
                    self._tbl.search()
                    .where(f"type = 'experience' AND key = '{key_safe}'")
                    .limit(1)
                    .to_list()
                )
            except Exception:
                return None
        if not rows:
            return None
        return self._experience_row_to_item(rows[0])

    def set_experience_deprecated(self, key: str, deprecated: bool) -> bool:
        item = self.get_experience_item(key)
        if item is None:
            return False
        key_safe = key.replace("'", "''")
        with self._store_lock:
            try:
                rows = (
                    self._tbl.search()
                    .where(f"type = 'experience' AND key = '{key_safe}'")
                    .limit(1)
                    .to_list()
                )
                if not rows:
                    return False
                self._update_experience(rows[0], deprecated=deprecated)
                return True
            except Exception as e:
                logger.warning("⚠️ 更新经验停用状态失败 / set deprecated failed: {}", e)
                return False

    def delete_experience(self, key: str) -> bool:
        if not key:
            return False
        key_safe = key.replace("'", "''")
        with self._store_lock:
            try:
                rows = (
                    self._tbl.search()
                    .where(f"type = 'experience' AND key = '{key_safe}'")
                    .limit(1)
                    .to_list()
                )
                if not rows:
                    return False
                self._tbl.delete(f"type = 'experience' AND key = '{key_safe}'")
                self._delete_vector_by_key(key)
                return True
            except Exception as e:
                logger.warning("⚠️ 删除经验失败 / delete experience failed: {}", e)
                return False

    def promote_experience_to_memory(
        self, key: str, category: str = "project"
    ) -> dict[str, Any] | None:
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
        return self.append_memory_category(category, line)

    def _fetch_experience_candidates(self, query: str, fetch: int) -> list[dict[str, Any]]:
        """Fetch experience candidates via vector or BM25 fallback."""
        if self._embed_fn and self._vec_tbl:
            try:
                vectors = self._compute_query_embeddings(query)
                vec = vectors[0] if vectors else None
                if not isinstance(vec, Sized) or len(vec) == 0:
                    raise ValueError("query embedding returned empty vector")
                with self._store_lock:
                    vec_rows = (
                        self._vec_tbl.search(vec)
                        .where("type = 'experience'")
                        .limit(fetch)
                        .to_list()
                    )
                if vec_rows:
                    if enriched := self._enrich_vector_results(vec_rows):
                        return enriched
            except Exception as e:
                logger.warning("⚠️ 经验检索失败 / experience search failed: {}", e)
        try:
            with self._store_lock:
                rows = self._tbl.search().where("type = 'experience'").limit(100).to_list()
            ranked = self._bm25_rank(query, rows)
            return [r for _, r in ranked] if ranked else rows
        except Exception as e:
            logger.warning("⚠️ 回退检索失败 / fallback search failed: {}", e)
            return []

    def _enrich_vector_results(self, vec_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Cross-reference vector results with main table to get columnar metadata."""
        try:
            keys = [str(vr.get("key", "")) for vr in vec_rows if vr.get("key")]
            key_map: dict[str, dict[str, Any]] = {}
            with self._store_lock:
                for key in keys:
                    key_safe = key.replace("'", "''")
                    rows = (
                        self._tbl.search()
                        .where(f"type = 'experience' AND key = '{key_safe}'")
                        .limit(1)
                        .to_list()
                    )
                    if rows:
                        key_map[key] = rows[0]
                needs_fallback = any(not vr.get("key") for vr in vec_rows)
                main_rows = (
                    self._tbl.search().where("type = 'experience'").limit(500).to_list()
                    if needs_fallback
                    else []
                )
            content_map: dict[str, dict[str, Any]] = {}
            for r in main_rows:
                c = r.get("content", "")
                if c:
                    content_map[c] = r
            enriched = []
            for vr in vec_rows:
                key = vr.get("key", "")
                vc = vr.get("content", "")
                matched = key_map.get(key) if key else content_map.get(vc)
                if matched:
                    enriched.append(matched)
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

    def _mutate_experiences(
        self,
        task_desc: str,
        threshold: float,
        mutator: Callable[[dict[str, Any]], dict[str, Any] | None],
        action: str,
    ) -> int:
        with self._store_lock:
            try:
                count = 0
                for r in self._match_experience_rows(task_desc, threshold=threshold):
                    updates = mutator(r)
                    if updates:
                        self._update_experience(r, **updates)
                        count += 1
                if count:
                    logger.info("📝 经验变更 / {}: {} for {}", action, count, task_desc[:60])
                return count
            except Exception as e:
                logger.warning("⚠️ 经验变更失败 / {} failed: {}", action, e)
                return 0

    def deprecate_similar(self, task_desc: str) -> int:
        return self._mutate_experiences(
            task_desc,
            threshold=0.5,
            mutator=lambda _r: {"deprecated": True},
            action="🧹 标记过时 / experiences deprecated",
        )

    def boost_experience(self, task_desc: str, delta: int = 1) -> int:
        def _mutator(r: dict[str, Any]) -> dict[str, Any] | None:
            old_q = r.get("quality", 3)
            new_q = max(1, min(5, old_q + delta))
            if new_q == old_q:
                return None
            return {"quality": new_q}

        return self._mutate_experiences(
            task_desc,
            threshold=0.4,
            mutator=_mutator,
            action=f"🧠 提升经验 / experience boosted ({delta:+d})",
        )

    def record_reuse(self, task_desc: str, success: bool) -> int:
        def _mutator(r: dict[str, Any]) -> dict[str, Any] | None:
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
            return updates

        sign = "+" if success else "-"
        return self._mutate_experiences(
            task_desc,
            threshold=0.4,
            mutator=_mutator,
            action=f"📝 记录复用 / reuse recorded ({sign})",
        )

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
                    hit_count = r.get("hit_count", 0)
                    has_hit_tracking = bool(r.get("last_hit_at"))
                    if quality >= 5 and uses >= 3 and not is_dep:
                        continue
                    should_remove = (
                        (is_dep and days_old > max_deprecated_days)
                        or (quality <= 1 and days_old > max_low_quality_days)
                        # New rules only apply to rows that have been through the hit-tracking
                        # era (last_hit_at non-empty). Pre-migration rows with hit_count=0
                        # are NOT considered "never retrieved" — they simply predate tracking.
                        or (has_hit_tracking and hit_count == 0 and days_old > 60 and quality <= 2)
                        or (has_hit_tracking and hit_count <= 1 and days_old > 120 and quality <= 3)
                    )
                    if should_remove and (key := r.get("key")):
                        self._tbl.delete(f"key = '{key}'")
                        self._delete_vector_by_key(key)
                        removed += 1
                if removed:
                    logger.info("🧹 清理经验 / stale experiences cleaned: {}", removed)
                return removed
            except Exception as e:
                logger.warning("⚠️ 清理经验失败 / cleanup failed: {}", e)
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
                logger.warning("⚠️ 候选检索失败 / merge candidates failed: {}", e)
                return []

    def replace_merged(
        self,
        old_entries: list[str],
        merged_content: str,
        *,
        category: str = "general",
        quality: int = 4,
    ) -> None:
        merged_key = ""
        with self._store_lock:
            try:
                rows = self._tbl.search().where("type = 'experience'").limit(200).to_list()
                content_to_key = {r.get("content"): r.get("key") for r in rows}
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
                logger.info("🔀 合并经验 / experiences merged: {} into 1", len(old_entries))
            except Exception as e:
                logger.warning("⚠️ 合并经验失败 / experience merge failed: {}", e)
                return
        self._embed_and_store(key=merged_key, content=merged_content, type_="experience")

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Split text into tokens. Handles both space-separated and CJK text.

        For space-separated languages: lowercase, strip punctuation, filter short tokens.
        For CJK characters: extract character bigrams per segment (no cross-boundary).
        For mixed tokens (e.g. 'Python编程'): extract both Latin and CJK parts.
        """
        tokens: list[str] = []
        for raw in text.split():
            if len(raw) < 2:
                continue
            w = raw.lower().strip(".,;:!?()[]{}\"'`~")
            if len(w) < 2:
                continue
            has_cjk = any(
                "\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff" or "\uac00" <= c <= "\ud7af"
                for c in w
            )
            if not has_cjk:
                tokens.append(w)
                continue
            # Mixed/CJK token: extract both Latin and CJK parts per segment
            seg_cjk: list[str] = []
            latin_buf: list[str] = []
            for c in w:
                if (
                    "\u4e00" <= c <= "\u9fff"
                    or "\u3040" <= c <= "\u30ff"
                    or "\uac00" <= c <= "\ud7af"
                ):
                    if latin_buf:
                        latin = "".join(latin_buf)
                        if len(latin) >= 2:
                            tokens.append(latin)
                        latin_buf = []
                    seg_cjk.append(c)
                else:
                    latin_buf.append(c)
            if latin_buf:
                latin = "".join(latin_buf)
                if len(latin) >= 2:
                    tokens.append(latin)
            # Bigrams per segment (no cross-boundary with other tokens)
            for i in range(len(seg_cjk) - 1):
                tokens.append(seg_cjk[i] + seg_cjk[i + 1])
            if len(seg_cjk) <= 4:
                tokens.extend(seg_cjk)
        return tokens

    @staticmethod
    def _normalize_low_information_query(query: str) -> str:
        return (
            query.lower()
            .replace(" ", "")
            .replace("\n", "")
            .strip(".,;:!?()[]{}\"'`~。？！；：、，…")
        )

    def should_skip_retrieval(self, query: str) -> bool:
        normalized = self._normalize_low_information_query(query)
        return not normalized or normalized in _LOW_INFORMATION_QUERIES

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
        self,
        query: str,
        type_filter: str | None = None,
        limit: int = 5,
        exclude_types: list[str] | None = None,
    ) -> list[str]:
        rows = self._fallback_text_candidates(
            query,
            type_filter=type_filter,
            limit=limit,
            exclude_types=exclude_types,
        )
        return [r["content"] for r in rows if r.get("content")]

    def _collect_long_term_parts(
        self, *, query_tokens: set[str] | None = None
    ) -> list[tuple[str, str]]:
        with self._store_lock:
            rows = self._read_long_term_rows_locked()
        content_by_category = {
            str(row.get("category") or "general"): str(row.get("content", "")).strip()
            for row in rows
        }
        parts: list[tuple[str, str]] = []
        for cat in MEMORY_CATEGORIES:
            content = content_by_category.get(cat, "")
            if not content:
                continue
            if query_tokens is not None and not (query_tokens & set(self._tokenize(content))):
                continue
            parts.append((cat, content))
        return parts

    @staticmethod
    def _format_long_term_parts(parts: list[tuple[str, str]], max_chars: int | None = None) -> str:
        if not parts:
            return ""

        header = "## Long-term Memory\n"
        if max_chars is None:
            result = "\n".join(f"[{cat}] {content}" for cat, content in parts)
            return f"{header}{result}"

        if max_chars <= len(header):
            return ""

        body_budget = max_chars - len(header)
        prefix_overhead = sum(len(f"[{cat}] ") for cat, _ in parts) + max(0, len(parts) - 1)
        usable = body_budget - prefix_overhead
        if usable <= 0:
            return ""

        total_raw = sum(len(content) for _, content in parts)
        budgeted: list[str] = []
        for cat, content in parts:
            if total_raw <= usable:
                budgeted.append(f"[{cat}] {content}")
                continue
            share = int(usable * len(content) / total_raw)
            if share <= 0:
                continue
            if len(content) > share:
                if share <= 1:
                    continue
                content = content[: share - 1] + "…"
            budgeted.append(f"[{cat}] {content}")

        result = "\n".join(budgeted)
        return f"{header}{result}" if budgeted else ""

    def get_memory_context(self, max_chars: int | None = None) -> str:
        parts = self._collect_long_term_parts()
        return self._format_long_term_parts(parts, max_chars=max_chars)

    def get_relevant_memory_context(self, query: str, max_chars: int | None = None) -> str:
        """Like get_memory_context but filters categories by relevance to query.
        Categories with no keyword overlap are skipped, saving tokens.
        Returns empty when the query is too weak or nothing matches.
        """
        if self.should_skip_retrieval(query):
            return ""
        query_tokens = set(self._tokenize(query))
        if not query_tokens:
            return ""
        parts = self._collect_long_term_parts(query_tokens=query_tokens)
        return self._format_long_term_parts(parts, max_chars=max_chars)

    # ── Explicit memory operations (for tools) ──

    def remember(self, content: str, category: str = "general") -> str:
        """Explicitly store a fact into long-term memory."""
        if category not in MEMORY_CATEGORIES:
            category = "general"
        cap = MEMORY_CATEGORY_CAPS.get(category, MEMORY_CATEGORY_CAPS["general"])
        with self._store_lock:
            existing = self._read_long_term_content_locked(category)
            updated = f"{existing}\n{content}" if existing else content
            normalized = self._normalize_memory(updated, max_chars=cap)
            changed = self._upsert_long_term_locked(category, normalized)
        if changed:
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
                logger.warning("⚠️ 遗忘失败 / forget failed: {}", e)
        if removed:
            self._embed_long_term_aggregate()
        return f"Removed {removed} memory entries matching '{query[:40]}'."

    def update_memory(self, category: str, content: str) -> str:
        """Replace entire content of a memory category."""
        if category not in MEMORY_CATEGORIES:
            return f"Invalid category. Use one of: {', '.join(MEMORY_CATEGORIES)}"
        cap = MEMORY_CATEGORY_CAPS.get(category, MEMORY_CATEGORY_CAPS["general"])
        normalized = self._normalize_memory(content, max_chars=cap)
        with self._store_lock:
            changed = self._upsert_long_term_locked(category, normalized)
        if changed:
            self._embed_long_term_aggregate()
        return f"Updated [{category}] memory."
