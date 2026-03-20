from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bao.agent.tools._web_common import (
    BROWSER_BLOCK_MARKERS,
    BROWSER_BLOCK_STATUSES,
    FILTER_LEVELS,
)
from bao.agent.tools._web_filters import smart_truncate


def parse_fetch_request(
    kwargs: dict[str, Any],
    *,
    masked_url: str,
    default_max_chars: int,
) -> dict[str, Any]:
    extract_mode_raw = kwargs.get("extractMode", "markdown")
    if not isinstance(extract_mode_raw, str):
        return {"error": "Invalid parameter 'extractMode': must be string", "url": masked_url}
    extract_mode = extract_mode_raw.strip().lower()
    if extract_mode not in ("markdown", "text"):
        return {"error": "Invalid parameter 'extractMode': must be one of [markdown, text]", "url": masked_url}

    max_chars_raw = kwargs.get("maxChars")
    if isinstance(max_chars_raw, bool) or (max_chars_raw is not None and not isinstance(max_chars_raw, int)):
        return {"error": "Invalid parameter 'maxChars': must be integer", "url": masked_url}
    if isinstance(max_chars_raw, int) and max_chars_raw < 100:
        return {"error": "Invalid parameter 'maxChars': must be >= 100", "url": masked_url}

    filter_level_raw = kwargs.get("filterLevel", "none")
    if not isinstance(filter_level_raw, str):
        return {"error": "Invalid parameter 'filterLevel': must be string", "url": masked_url}
    filter_level = filter_level_raw.strip().lower()
    if filter_level not in FILTER_LEVELS:
        return {"error": "Invalid parameter 'filterLevel': must be one of [none, standard, aggressive]", "url": masked_url}

    return {
        "extract_mode": extract_mode,
        "filter_level": filter_level,
        "max_chars": max_chars_raw if isinstance(max_chars_raw, int) else default_max_chars,
    }


def truncate_output(text: str, filter_level: str, max_chars: int) -> tuple[str, bool]:
    if filter_level != "none":
        return smart_truncate(text, max_chars)
    truncated = len(text) > max_chars
    return (text[:max_chars], True) if truncated else (text, False)


@dataclass
class SuccessPayloadRequest:
    masked_url: str
    final_url: str
    status: int
    extractor: str
    backend: str
    fallback_reason: str | None
    filter_level: str
    filtered: bool
    truncated: bool
    text: str


def build_success_payload(request: SuccessPayloadRequest) -> dict[str, Any]:
    return {
        "url": request.masked_url,
        "finalUrl": request.final_url,
        "status": request.status,
        "extractor": request.extractor,
        "backend": request.backend,
        "fallbackUsed": request.fallback_reason is not None,
        "fallbackReason": request.fallback_reason,
        "filterLevel": request.filter_level,
        "filtered": request.filtered,
        "truncated": request.truncated,
        "length": len(request.text),
        "text": request.text,
    }


def browser_fallback_reason(
    *,
    browser_available: bool,
    status: int | None,
    raw_html: str,
    extracted_text: str,
    error_text: str = "",
) -> str | None:
    if not browser_available:
        return None
    if isinstance(status, int) and status in BROWSER_BLOCK_STATUSES:
        return f"status_{status}"
    normalized_html = raw_html.lower()
    if any(marker in normalized_html for marker in BROWSER_BLOCK_MARKERS):
        return "challenge_detected"
    if error_text and any(marker in error_text.lower() for marker in BROWSER_BLOCK_MARKERS):
        return "challenge_error"
    if raw_html and len(extracted_text.strip()) < 80 and len(raw_html) > 1200:
        return "empty_readability_result"
    return None
