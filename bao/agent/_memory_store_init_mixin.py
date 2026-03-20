from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from bao.agent._memory_experience_domain import _ExperienceMemoryDomain
from bao.agent._memory_long_term_domain import _LongTermMemoryDomain
from bao.agent._memory_recall_domain import _RecallDomain
from bao.agent._memory_shared import (
    _DEFAULT_EMBED_TIMEOUT_S,
    DEFAULT_MEMORY_POLICY,
    MemoryChangeEvent,
    MemoryPolicy,
    _normalized_storage_root,
)
from bao.utils.db import get_db

_CHANGE_LISTENER_LOCK = threading.RLock()
_CHANGE_LISTENERS: dict[str, list[Callable[[MemoryChangeEvent], None]]] = {}


class _MemoryStoreInitMixin:
    def __init__(
        self,
        workspace: Path,
        embedding_config: Any | None = None,
        memory_policy: MemoryPolicy | None = None,
    ) -> None:
        self._store_lock = threading.RLock()
        self._memory_policy = memory_policy or DEFAULT_MEMORY_POLICY
        self._storage_root = _normalized_storage_root(workspace)
        self._db: Any = get_db(workspace)
        self._tbl: Any = self._ensure_migrated_table()
        self._embed_fn = None
        self._vec_tbl: Any | None = None
        self._embed_timeout_s = _DEFAULT_EMBED_TIMEOUT_S
        self._query_embed_cache: dict[str, tuple[float, list[list[float]]]] = {}
        self._query_embed_cache_lock = threading.Lock()
        self._retrieval_revision = 0
        self._retrieval_index: dict[str, Any] | None = None
        self._pending_hit_updates: dict[str, dict[str, Any]] = {}
        self._hit_stats_lock = threading.Lock()
        self._hit_flush_inflight = False
        self._migrate_long_term_facts()
        self._init_domains()
        if embedding_config and getattr(embedding_config, "enabled", False):
            self._init_embedding(embedding_config)

    def close(self) -> None:
        with self._store_lock:
            self._vec_tbl = None
            self._embed_fn = None
            self._invalidate_retrieval_index()

    def add_change_listener(self, listener: Callable[[MemoryChangeEvent], None]) -> None:
        storage_root = str(getattr(self, "_storage_root", "") or "")
        if not storage_root:
            return
        with _CHANGE_LISTENER_LOCK:
            listeners = _CHANGE_LISTENERS.setdefault(storage_root, [])
            if listener not in listeners:
                listeners.append(listener)

    def remove_change_listener(self, listener: Callable[[MemoryChangeEvent], None]) -> None:
        storage_root = str(getattr(self, "_storage_root", "") or "")
        if not storage_root:
            return
        with _CHANGE_LISTENER_LOCK:
            listeners = _CHANGE_LISTENERS.get(storage_root)
            if not listeners:
                return
            if listener in listeners:
                listeners.remove(listener)
            if not listeners:
                _CHANGE_LISTENERS.pop(storage_root, None)

    def _emit_change(
        self,
        *,
        scope: str,
        operation: str,
        category: str = "",
        key: str = "",
    ) -> None:
        storage_root = str(getattr(self, "_storage_root", "") or "")
        if not storage_root:
            return
        event = MemoryChangeEvent(
            storage_root=storage_root,
            scope=scope,
            operation=operation,
            category=category,
            key=key,
            updated_at=datetime.now().isoformat(),
        )
        with _CHANGE_LISTENER_LOCK:
            listeners = tuple(_CHANGE_LISTENERS.get(storage_root, ()))
        for listener in listeners:
            try:
                listener(event)
            except Exception as exc:
                logger.debug("memory change listener skipped: {}", exc)

    def _init_domains(self) -> None:
        self._long_term_domain = _LongTermMemoryDomain(self)
        self._experience_domain = _ExperienceMemoryDomain(self)
        self._recall_domain = _RecallDomain(self)

    def _memory_cap(self, category: str) -> int:
        policy = getattr(self, "_memory_policy", DEFAULT_MEMORY_POLICY)
        if isinstance(policy, MemoryPolicy):
            return policy.category_cap(category)
        return DEFAULT_MEMORY_POLICY.category_cap(category)

    def _ensure_domains(self) -> None:
        if not hasattr(self, "_long_term_domain"):
            self._init_domains()

    def _long_term(self) -> _LongTermMemoryDomain:
        self._ensure_domains()
        return self._long_term_domain

    def _experience(self) -> _ExperienceMemoryDomain:
        self._ensure_domains()
        return self._experience_domain

    def _recall(self) -> _RecallDomain:
        self._ensure_domains()
        return self._recall_domain
