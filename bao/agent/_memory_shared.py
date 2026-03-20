"""Shared memory constants, policy, and value types."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

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
_QUERY_EMBED_CACHE_TTL_S = 120.0
_QUERY_EMBED_CACHE_MAX = 256
_BACKFILL_SCAN_LIMIT = 20000
_MIGRATION_CHUNK_SIZE = 1000

_RETENTION_DAYS = {5: 365, 4: 180, 3: 90, 2: 30, 1: 14}
MEMORY_CATEGORIES = ("preference", "personal", "project", "general")
_DEFAULT_MEMORY_CATEGORY_CAPS = {
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
_CATEGORY_WEIGHTS: dict[str, float] = {
    "preference": 1.0,
    "project": 0.8,
    "personal": 0.6,
    "general": 0.4,
}


def _coerce_positive_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return max(1, value)
    if isinstance(value, str):
        raw = value.strip()
        if raw.isdigit():
            return max(1, int(raw))
    return default


def _coerce_nonempty_str(value: Any, default: str) -> str:
    if isinstance(value, str):
        raw = value.strip()
        if raw:
            return raw
    return default


@dataclass(frozen=True)
class MemoryPolicy:
    recent_window: int = 100
    learning_mode: str = "utility"
    related_memory_limit: int = 5
    related_experience_limit: int = 3
    related_memory_chars: int = 2000
    related_experience_chars: int = 1500
    long_term_chars: int = 1500
    category_caps: dict[str, int] = field(
        default_factory=lambda: dict(_DEFAULT_MEMORY_CATEGORY_CAPS)
    )

    @classmethod
    def from_agent_defaults(cls, defaults: Any | None) -> "MemoryPolicy":
        policy = cls()
        if defaults is None:
            return policy
        memory_settings = getattr(defaults, "memory", None)
        return cls(
            recent_window=_coerce_positive_int(
                getattr(memory_settings, "recent_window", None),
                _coerce_positive_int(getattr(defaults, "memory_window", None), policy.recent_window),
            ),
            learning_mode=_coerce_nonempty_str(
                getattr(memory_settings, "learning_mode", None),
                _coerce_nonempty_str(getattr(defaults, "experience_model", None), policy.learning_mode),
            ),
            related_memory_limit=policy.related_memory_limit,
            related_experience_limit=policy.related_experience_limit,
            related_memory_chars=policy.related_memory_chars,
            related_experience_chars=policy.related_experience_chars,
            long_term_chars=policy.long_term_chars,
            category_caps=dict(policy.category_caps),
        )

    def with_recent_window(self, value: Any) -> "MemoryPolicy":
        return replace(self, recent_window=_coerce_positive_int(value, self.recent_window))

    def with_learning_mode(self, value: Any) -> "MemoryPolicy":
        return replace(self, learning_mode=_coerce_nonempty_str(value, self.learning_mode))

    def category_cap(self, category: str) -> int:
        return int(self.category_caps.get(category, self.category_caps["general"]))


DEFAULT_MEMORY_POLICY = MemoryPolicy()
MEMORY_CATEGORY_CAPS = dict(DEFAULT_MEMORY_POLICY.category_caps)


@dataclass(frozen=True)
class RecallBundle:
    long_term_context: str = ""
    related_memory: tuple[str, ...] = ()
    related_experience: tuple[str, ...] = ()


def summarize_recall_bundle(bundle: RecallBundle) -> dict[str, Any]:
    categories: list[str] = []
    for line in str(bundle.long_term_context or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("[") or "]" not in stripped:
            continue
        category = stripped[1:].split("]", 1)[0].strip()
        if category in MEMORY_CATEGORIES and category not in categories:
            categories.append(category)
    related_memory_count = len(bundle.related_memory)
    experience_count = len(bundle.related_experience)
    if not categories and related_memory_count <= 0 and experience_count <= 0:
        return {}
    return {
        "longTermCategories": categories,
        "relatedMemoryCount": related_memory_count,
        "experienceCount": experience_count,
    }


@dataclass(frozen=True)
class MemoryChangeEvent:
    storage_root: str
    scope: str
    operation: str
    category: str = ""
    key: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class _RecallQueryContext:
    query: str
    query_terms: tuple[str, ...]
    query_term_set: frozenset[str]
    query_vectors: list[list[float]] | None = None


def _normalized_storage_root(workspace: Path) -> str:
    try:
        return str(workspace.expanduser().resolve())
    except OSError:
        return str(workspace.expanduser())
