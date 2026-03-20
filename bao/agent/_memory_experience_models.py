from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ExperienceAppendRequest:
    task: str
    outcome: str
    lessons: str
    quality: int = 3
    category: str = "general"
    keywords: str = ""
    reasoning_trace: str = ""


@dataclass(frozen=True, slots=True)
class ExperienceListRequest:
    query: str = ""
    category: str = ""
    outcome: str = ""
    deprecated: bool | None = None
    min_quality: int = 0
    sort_by: str = "updated_desc"
    limit: int = 200


@dataclass(frozen=True, slots=True)
class Bm25RankRequest:
    query: str
    docs: list[dict[str, Any]]
    k1: float = 1.2
    b: float = 0.75
    query_terms: list[str] | None = None
    doc_tokens: list[list[str] | tuple[str, ...]] | None = None


@dataclass(frozen=True, slots=True)
class Bm25ScoreRequest:
    docs: list[dict[str, Any]]
    doc_tokens: list[list[str] | tuple[str, ...]]
    query_terms: list[str]
    df: dict[str, int]
    avgdl: float
    k1: float
    b: float
