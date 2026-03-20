"""Memory system — LanceDB backend with columnar experience schema."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from bao.agent._memory_experience_models import (
    Bm25RankRequest,
    Bm25ScoreRequest,
    ExperienceAppendRequest,
    ExperienceListRequest,
)
from bao.agent._memory_shared import (
    _BACKFILL_SCAN_LIMIT,
    DEFAULT_MEMORY_POLICY,
    MEMORY_CATEGORIES,
    MEMORY_CATEGORY_CAPS,
    MemoryChangeEvent,
    MemoryPolicy,
    RecallBundle,
    summarize_recall_bundle,
)
from bao.agent._memory_store_embedding_mixin import _MemoryStoreEmbeddingMixin
from bao.agent._memory_store_experience_support_mixin import _MemoryStoreExperienceSupportMixin
from bao.agent._memory_store_facade_mixin import _MemoryStoreFacadeMixin
from bao.agent._memory_store_init_mixin import _MemoryStoreInitMixin
from bao.agent._memory_store_long_term_support_mixin import _MemoryStoreLongTermSupportMixin
from bao.agent._memory_store_query_context_mixin import _MemoryStoreQueryContextMixin
from bao.agent._memory_store_retrieval_index_mixin import _MemoryStoreRetrievalIndexMixin
from bao.agent._memory_store_schema_mixin import _MemoryStoreSchemaMixin
from bao.agent._memory_store_search_support_mixin import _MemoryStoreSearchSupportMixin
from bao.agent._memory_store_text_support_mixin import _MemoryStoreTextSupportMixin


class MemoryStore(
    _MemoryStoreInitMixin,
    _MemoryStoreSchemaMixin,
    _MemoryStoreEmbeddingMixin,
    _MemoryStoreQueryContextMixin,
    _MemoryStoreRetrievalIndexMixin,
    _MemoryStoreLongTermSupportMixin,
    _MemoryStoreExperienceSupportMixin,
    _MemoryStoreTextSupportMixin,
    _MemoryStoreSearchSupportMixin,
    _MemoryStoreFacadeMixin,
):
    _EMBED_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="Bao-embed")
    _MEMORY_BG_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="Bao-memory-bg")


__all__ = [
    "DEFAULT_MEMORY_POLICY",
    "Bm25RankRequest",
    "Bm25ScoreRequest",
    "ExperienceAppendRequest",
    "ExperienceListRequest",
    "MEMORY_CATEGORIES",
    "MEMORY_CATEGORY_CAPS",
    "MemoryChangeEvent",
    "MemoryPolicy",
    "MemoryStore",
    "RecallBundle",
    "_BACKFILL_SCAN_LIMIT",
    "summarize_recall_bundle",
]
