from __future__ import annotations

import html
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from bao.config.schema import WebSearchConfig

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5
FILTER_LEVELS = ("none", "standard", "aggressive")
BROWSER_BLOCK_STATUSES = frozenset({403, 429, 503})
BROWSER_BLOCK_MARKERS = (
    "just a moment",
    "verify you are human",
    "cf-challenge",
    "cloudflare",
    "captcha",
    "access denied",
    "perimeterx",
    "datadome",
    "attention required",
)
_CREDENTIALS_IN_URL_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)([^/@\s]+)@")


def strip_tags(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def normalize(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def validate_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, f"Only http/https allowed, got '{parsed.scheme or 'none'}'"
        if not parsed.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as exc:
        return False, str(exc)


def mask_url_credentials(text: str) -> str:
    return _CREDENTIALS_IN_URL_RE.sub(r"\1***:***@", text)


def safe_error_text(error: Exception) -> str:
    return mask_url_credentials(str(error))


def make_async_client(proxy: str | None, **kwargs: Any) -> httpx.AsyncClient:
    async_client_ctor: Any = httpx.AsyncClient
    if not proxy:
        return async_client_ctor(**kwargs)
    try:
        return async_client_ctor(proxy=proxy, **kwargs)
    except TypeError:
        fallback_kwargs = dict(kwargs)
        fallback_kwargs["proxies"] = {"http://": proxy, "https://": proxy}
        return async_client_ctor(**fallback_kwargs)


def resolve_search_config(
    search_config: WebSearchConfig | None,
    proxy: str | None,
) -> dict[str, Any]:
    brave_key = search_config.brave_api_key.get_secret_value() if search_config else None
    tavily_key = search_config.tavily_api_key.get_secret_value() if search_config else None
    exa_key = search_config.exa_api_key.get_secret_value() if search_config else None
    return {
        "provider": search_config.provider if search_config else "",
        "brave_key": brave_key or os.environ.get("BRAVE_API_KEY", ""),
        "tavily_key": tavily_key or os.environ.get("TAVILY_API_KEY", ""),
        "exa_key": exa_key or os.environ.get("EXA_API_KEY", ""),
        "max_results": search_config.max_results if search_config else 5,
        "proxy": (proxy or "").strip() or None,
        "exa_max_characters": 1000,
    }
