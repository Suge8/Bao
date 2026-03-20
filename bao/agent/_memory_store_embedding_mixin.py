from __future__ import annotations

from collections.abc import Sized
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Callable

from loguru import logger

from bao.agent._memory_embedding import _GeminiEmbedding
from bao.agent._memory_shared import (
    _BACKFILL_SCAN_LIMIT,
    _DEFAULT_EMBED_TIMEOUT_S,
    _ENV_BASE,
    _ENV_KEY,
)
from bao.utils.db import ensure_table


class _MemoryStoreEmbeddingMixin:
    @staticmethod
    def _backfill_scan_limit() -> int:
        from bao.agent import memory as memory_module

        return int(getattr(memory_module, "_BACKFILL_SCAN_LIMIT", _BACKFILL_SCAN_LIMIT))

    def _init_embedding(self, cfg: Any) -> None:
        try:
            self._embed_timeout_s = max(
                1, int(getattr(cfg, "timeout_seconds", _DEFAULT_EMBED_TIMEOUT_S))
            )
            api_key = cfg.api_key.get_secret_value()
            model_lower = cfg.model.lower()
            if "gemini" in model_lower or "models/embedding" in model_lower:
                model_name = cfg.model if cfg.model.startswith("models/") else f"models/{cfg.model}"
                self._embed_fn = _GeminiEmbedding(model=model_name, api_key=api_key)
                backend = "gemini-genai"
            else:
                from lancedb.embeddings import get_registry

                registry = get_registry()
                backend, kwargs = self._resolve_embedding_backend(registry, cfg)
                self._embed_fn = registry.get(backend).create(**kwargs)

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
        except Exception as exc:
            logger.warning("⚠️ 向量初始化失败 / embedding init failed: {}", exc)
            self._embed_fn = None
            self._vec_tbl = None

    @classmethod
    def _run_with_timeout(cls, timeout_s: int, fn: Callable[[], Any]) -> Any:
        fut = cls._EMBED_EXECUTOR.submit(fn)
        try:
            return fut.result(timeout=timeout_s)
        except FuturesTimeoutError as exc:
            fut.cancel()
            raise TimeoutError(f"Embedding request timed out after {timeout_s}s") from exc

    @staticmethod
    def _is_transient_embedding_error(exc: Exception) -> bool:
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

    def _call_embedding(self, fn: Callable[[], Any], *, op: str) -> Any:
        try:
            return type(self)._run_with_timeout(self._embed_timeout_s, fn)
        except Exception as exc:
            if self._is_transient_embedding_error(exc):
                logger.debug("Embedding {} failed without hidden retry: {}", op, exc)
            raise

    def _compute_source_embeddings(self, texts: list[str]) -> list[list[float]]:
        embed_fn = self._embed_fn
        if not embed_fn:
            return []
        return self._call_embedding(
            lambda: embed_fn.compute_source_embeddings(texts),
            op="source",
        )

    @staticmethod
    def _log_background_exception(fut: Any) -> None:
        try:
            fut.result()
        except Exception as exc:
            logger.debug("memory background task skipped: {}", exc)

    def _schedule_hit_stats_update(self, rows: list[dict[str, Any]]) -> None:
        self._ensure_hit_stats_state()
        should_submit = False
        with self._hit_stats_lock:
            for row in rows:
                key = str(row.get("key") or "")
                if not key:
                    continue
                pending = self._pending_hit_updates.get(key)
                hit_delta = int((pending or {}).get("_hit_delta", 0) or 0) + 1
                merged = dict(pending or {})
                merged.update(dict(row))
                merged["key"] = key
                merged["_hit_delta"] = hit_delta
                self._pending_hit_updates[key] = merged
            if not self._pending_hit_updates or self._hit_flush_inflight:
                return
            self._hit_flush_inflight = True
            should_submit = True
        if not should_submit:
            return
        fut = self._MEMORY_BG_EXECUTOR.submit(self._flush_pending_hit_stats)
        fut.add_done_callback(self._log_background_exception)

    def _flush_pending_hit_stats(self) -> None:
        self._ensure_hit_stats_state()
        while True:
            with self._hit_stats_lock:
                if not self._pending_hit_updates:
                    self._hit_flush_inflight = False
                    return
                batch = list(self._pending_hit_updates.values())
                self._pending_hit_updates = {}
            self._update_hit_stats(batch)

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
            main_by_key = {
                row.get("key", ""): row
                for row in rows
                if row.get("key", "")
                and str(row.get("content", "")).strip()
                and row.get("type", "")
            }
            with self._store_lock:
                vec_rows = self._vec_tbl.search().limit(self._backfill_scan_limit()).to_list()
            vec_by_key = {
                row.get("key", ""): row
                for row in vec_rows
                if row.get("key") and row.get("key") != "_init_"
            }
            backfilled = 0
            refreshed = 0
            for key, row in main_by_key.items():
                content = row.get("content", "")
                type_ = row.get("type", "")
                existing = vec_by_key.get(key)
                if not existing:
                    self._store_vector_for_row(key=key, content=content, type_=type_)
                    backfilled += 1
                    continue
                if existing.get("content", "") != content or existing.get("type", "") != type_:
                    self._store_vector_for_row(key=key, content=content, type_=type_)
                    refreshed += 1
            if backfilled:
                logger.info("🧠 补全向量 / embeddings backfilled: {} records", backfilled)
            if refreshed:
                logger.info("♻️ 刷新向量 / embeddings refreshed: {} records", refreshed)
        except Exception as exc:
            logger.warning("⚠️ 向量补全失败 / embedding backfill failed: {}", exc)

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

    def _embed_and_store(self, *, key: str, content: str, type_: str) -> None:
        if not self._embed_fn or not self._vec_tbl or not content.strip():
            return
        try:
            self._store_vector_for_row(key=key, content=content, type_=type_)
        except Exception as exc:
            logger.warning("⚠️ 向量写入失败 / embedding store failed: {}", exc)
