from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CaseResultRequest:
    case: dict[str, Any]
    mode: str
    domains: list[str]
    selected_domains: list[str]
    visible_tool_count: int
    prompt_chars: int
    reasons: list[str]


@dataclass(frozen=True, slots=True)
class CaseEvaluationOutcome:
    result: dict[str, Any]
    visible_tool_count: int
    prompt_chars: int


@dataclass(frozen=True, slots=True)
class EvalSummaryRequest:
    run_id: str
    case_results: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    visible_tool_total: int
    prompt_chars_total: int
    mode_override: str | None
    domains_override: list[str] | None
    selected_default_domains: list[str]
