"""Web tools: web_search and web_fetch."""

import html
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger

from bao.agent.tools.agent_browser import AgentBrowserRunner, agent_browser_available
from bao.agent.tools.base import Tool
from bao.config.schema import WebSearchConfig

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5
_CREDENTIALS_IN_URL_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)([^/@\s]+)@")


def _strip_tags(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _validate_url(url: str) -> tuple[bool, str]:
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as e:
        return False, str(e)


def _mask_url_credentials(text: str) -> str:
    return _CREDENTIALS_IN_URL_RE.sub(r"\1***:***@", text)


def _safe_error_text(error: Exception) -> str:
    return _mask_url_credentials(str(error))


def _make_async_client(proxy: str | None, **kwargs: Any) -> httpx.AsyncClient:
    async_client_ctor: Any = httpx.AsyncClient
    if not proxy:
        return async_client_ctor(**kwargs)
    try:
        return async_client_ctor(proxy=proxy, **kwargs)
    except TypeError:
        fallback_kwargs = dict(kwargs)
        fallback_kwargs["proxies"] = {"http://": proxy, "https://": proxy}
        return async_client_ctor(**fallback_kwargs)


# ---------------------------------------------------------------------------
# Layer 1 – HTML pre-cleaning (before Readability)
#   Only removes tags Readability already ignores. Does NOT touch structural
#   tags (nav/footer/aside) so DOM scoring stays intact.
# ---------------------------------------------------------------------------

_PRECLEAN_RE = re.compile(
    r"<(?:script|style|noscript|iframe|svg)[\s>][\s\S]*?</(?:script|style|noscript|iframe|svg)>",
    re.I,
)


def _preclean_html(raw_html: str) -> str:
    return _PRECLEAN_RE.sub("", raw_html)


# ---------------------------------------------------------------------------
# Layer 2① – Boilerplate line filter (after Readability → text)
#   Short lines matching strong patterns, only in first/last 500 chars.
# ---------------------------------------------------------------------------

# .*$ (not \s*$) so "Copyright © 2024 Acme" matches fully
_BOILERPLATE_RE = re.compile(
    r"^\s*("
    r"accept\s+(all\s+)?cookies"
    r"|cookie\s+(settings|preferences|policy)"
    r"|share\s+(on|via|to)\s"
    r"|follow\s+us\b"
    r"|subscribe\s+(to|now|for)"
    r"|sign\s+up\s+(for|now|free)"
    r"|copyright\s*[©(]"
    r"|all\s+rights\s+reserved"
    r"|terms\s+(of\s+)?(use|service)"
    r"|privacy\s+policy"
    r"|cookie\s+policy"
    r"|powered\s+by\b"
    r"|advertisement"
    r"|loading\.{2,}"
    r"|please\s+wait"
    r").*$",
    re.I,
)
_BOILERPLATE_MAX_LINE_LEN = 100
_BOILERPLATE_WINDOW = 500


def _is_boilerplate_line(line: str) -> bool:
    stripped = line.strip()
    return (
        0 < len(stripped) <= _BOILERPLATE_MAX_LINE_LEN
        and _BOILERPLATE_RE.search(stripped) is not None
    )


def _filter_boilerplate(text: str) -> str:
    if len(text) < _BOILERPLATE_WINDOW * 2:
        return "\n".join(ln for ln in text.split("\n") if not _is_boilerplate_line(ln))

    head_end = text.find("\n", _BOILERPLATE_WINDOW)
    if head_end == -1:
        head_end = _BOILERPLATE_WINDOW
    tail_start = text.rfind("\n", 0, len(text) - _BOILERPLATE_WINDOW)
    if tail_start == -1:
        tail_start = len(text) - _BOILERPLATE_WINDOW

    head_lines = [ln for ln in text[:head_end].split("\n") if not _is_boilerplate_line(ln)]
    tail_lines = [ln for ln in text[tail_start:].split("\n") if not _is_boilerplate_line(ln)]

    return "\n".join(head_lines) + text[head_end:tail_start] + "\n".join(tail_lines)


# ---------------------------------------------------------------------------
# Layer 2② – Adjacent duplicate paragraph dedup
# ---------------------------------------------------------------------------


def _dedup_adjacent(text: str) -> str:
    paragraphs = text.split("\n\n")
    if len(paragraphs) <= 1:
        return text
    result = [paragraphs[0]]
    for para in paragraphs[1:]:
        if para.strip().lower() != result[-1].strip().lower():
            result.append(para)
    return "\n\n".join(result)


# ---------------------------------------------------------------------------
# Layer 2③ – Link-heavy paragraph removal (aggressive only)
#   ≥80% markdown links AND ≥3 links → navigation debris.
#   Protected if preceding heading hints at references/resources.
# ---------------------------------------------------------------------------

_LINK_RE = re.compile(r"\[.*?\]\(.*?\)")
_REF_HEADING_RE = re.compile(
    r"(references?|links?|resources?|参考|资源|相关链接|see also)",
    re.I,
)


def _is_link_heavy(para: str) -> bool:
    stripped = para.strip()
    if not stripped:
        return False
    links = _LINK_RE.findall(stripped)
    if len(links) < 3:
        return False
    return sum(len(m) for m in links) / len(stripped) >= 0.8


def _filter_link_heavy(text: str) -> str:
    paragraphs = text.split("\n\n")
    result: list[str] = []
    for i, para in enumerate(paragraphs):
        if _is_link_heavy(para) and not (i > 0 and _REF_HEADING_RE.search(paragraphs[i - 1])):
            continue
        result.append(para)
    return "\n\n".join(result)


# ---------------------------------------------------------------------------
# Layer 3 – Smart truncation
#   Natural break in [0.85*max, max]: paragraph → line → sentence → hard cut.
# ---------------------------------------------------------------------------

_SENTENCE_END_RE = re.compile(r"[.!?。！？]\s")
_TRUNCATED_SUFFIX = "\n\n[... truncated]"


def _smart_truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False

    floor = int(max_chars * 0.85)

    cut = text.rfind("\n\n", floor, max_chars)
    if cut != -1:
        return text[:cut].rstrip() + _TRUNCATED_SUFFIX, True

    cut = text.rfind("\n", floor, max_chars)
    if cut != -1:
        return text[:cut].rstrip() + _TRUNCATED_SUFFIX, True

    matches = list(_SENTENCE_END_RE.finditer(text[floor:max_chars]))
    if matches:
        return text[: floor + matches[-1].end()].rstrip() + _TRUNCATED_SUFFIX, True

    return text[:max_chars] + _TRUNCATED_SUFFIX, True


# ---------------------------------------------------------------------------
# Filter pipeline orchestrator
# ---------------------------------------------------------------------------


def _apply_filters(text: str, level: str) -> tuple[str, bool]:
    if level == "none":
        return text, False

    original = text
    text = _normalize(_dedup_adjacent(_filter_boilerplate(text)))

    if level == "aggressive":
        text = _normalize(_filter_link_heavy(text))

    return text, text != original


# ═══════════════════════════════════════════════════════════════════════════
# WebSearchTool
# ═══════════════════════════════════════════════════════════════════════════


class WebSearchTool(Tool):
    """Search the web using Brave, Tavily, or Exa API."""

    _NAME = "web_search"
    _DESCRIPTION = (
        "Search the web. ALWAYS use this instead of exec+curl. Returns titles, URLs, and snippets."
    )
    _PARAMETERS: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {
                "type": "integer",
                "description": "Results (1-10)",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
    }

    @property
    def name(self) -> str:
        return self._NAME

    @property
    def description(self) -> str:
        return self._DESCRIPTION

    @property
    def parameters(self) -> dict[str, Any]:
        return self._PARAMETERS

    def __init__(self, search_config: "WebSearchConfig | None" = None, proxy: str | None = None):
        self.provider = search_config.provider if search_config else ""
        brave_key = search_config.brave_api_key.get_secret_value() if search_config else None
        self.brave_key = brave_key or os.environ.get("BRAVE_API_KEY", "")
        self.tavily_key = (
            search_config.tavily_api_key.get_secret_value() if search_config else None
        ) or os.environ.get("TAVILY_API_KEY", "")
        self.max_results = search_config.max_results if search_config else 5
        exa_key = search_config.exa_api_key.get_secret_value() if search_config else None
        self.exa_key = exa_key or os.environ.get("EXA_API_KEY", "")
        self.exa_max_characters = 1000
        self.proxy = (proxy or "").strip() or None

    async def execute(self, **kwargs: Any) -> str:
        unexpected = sorted(set(kwargs) - {"query", "count"})
        if unexpected:
            return f"Error: Unexpected parameter(s): {', '.join(unexpected)}"

        query_raw = kwargs.get("query", "")
        query = query_raw if isinstance(query_raw, str) else str(query_raw)
        if not query.strip():
            return "Error: Missing required parameter 'query'"

        count_raw = kwargs.get("count")
        if isinstance(count_raw, bool) or (
            count_raw is not None and not isinstance(count_raw, int)
        ):
            return "Error: Invalid parameter 'count': must be integer"
        count = count_raw if isinstance(count_raw, int) else None

        n = min(max(count or self.max_results, 1), 10)
        p = (self.provider or "").lower()
        dispatch = {"tavily": self._tavily, "brave": self._brave, "exa": self._exa}
        keys = {"tavily": self.tavily_key, "brave": self.brave_key, "exa": self.exa_key}
        # Build try order: explicit provider first, then default priority
        default_order = [k for k in ("tavily", "brave", "exa") if keys.get(k)]
        if p in dispatch and keys.get(p):
            order = [p] + [k for k in default_order if k != p]
        else:
            order = default_order
        for provider in order:
            result = await dispatch[provider](query, n)
            if not result.startswith("Error:"):
                return result
        return "Error: No search API key configured (set provider + API key in config)"

    async def _brave(self, query: str, n: int) -> str:
        try:
            logger.debug("WebSearch: {}", "proxy enabled" if self.proxy else "direct connection")
            async with _make_async_client(self.proxy) as client:
                r = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers={"Accept": "application/json", "X-Subscription-Token": self.brave_key},
                    timeout=10.0,
                )
                r.raise_for_status()
            results = r.json().get("web", {}).get("results", [])[:n]
            return self._format(query, results, n)
        except httpx.ProxyError as e:
            safe = _safe_error_text(e)
            logger.error("WebSearch proxy error: {}", safe)
            return f"Error: Proxy error: {safe}"
        except Exception as e:
            return f"Error: {_safe_error_text(e)}"

    async def _tavily(self, query: str, n: int) -> str:
        try:
            logger.debug("WebSearch: {}", "proxy enabled" if self.proxy else "direct connection")
            async with _make_async_client(self.proxy) as client:
                r = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.tavily_key,
                        "query": query,
                        "max_results": n,
                        "include_answer": True,
                    },
                    timeout=15.0,
                )
                r.raise_for_status()
            data = r.json()
            results = [
                {
                    "title": x.get("title", ""),
                    "url": x.get("url", ""),
                    "description": x.get("content", ""),
                }
                for x in data.get("results", [])
            ]
            answer = data.get("answer", "")
            out = self._format(query, results, n)
            if answer:
                out = f"[AI Summary] {answer}\n\n---\n\n{out}"
            return out
        except httpx.ProxyError as e:
            safe = _safe_error_text(e)
            logger.error("WebSearch proxy error: {}", safe)
            return f"Error: Proxy error: {safe}"
        except Exception as e:
            return f"Error: {_safe_error_text(e)}"

    async def _exa(self, query: str, n: int) -> str:
        try:
            logger.debug("WebSearch: {}", "proxy enabled" if self.proxy else "direct connection")
            async with _make_async_client(self.proxy) as client:
                r = await client.post(
                    "https://api.exa.ai/search",
                    json={
                        "query": query,
                        "numResults": n,
                        "contents": {"text": {"maxCharacters": self.exa_max_characters}},
                    },
                    headers={"x-api-key": self.exa_key, "Content-Type": "application/json"},
                    timeout=15.0,
                )
                r.raise_for_status()
            data = r.json()
            results = [
                {
                    "title": x.get("title", ""),
                    "url": x.get("url", ""),
                    "description": x.get("text", ""),
                }
                for x in data.get("results", [])
            ]
            return self._format(query, results, n)
        except httpx.ProxyError as e:
            safe = _safe_error_text(e)
            logger.error("WebSearch proxy error: {}", safe)
            return f"Error: Proxy error: {safe}"
        except Exception as e:
            return f"Error: {_safe_error_text(e)}"

    @staticmethod
    def _format(query: str, results: list[dict[str, str]], n: int) -> str:
        if not results:
            return f"No results for: {query}"
        lines = [f"Results for: {query}\n"]
        for i, item in enumerate(results[:n], 1):
            lines.append(f"[{i}] {item.get('title', '')}\n   {item.get('url', '')}")
            if desc := item.get("description"):
                lines.append(f"   {desc}")
            lines.append("")
        return "\n".join(lines).rstrip()


# ═══════════════════════════════════════════════════════════════════════════
# WebFetchTool
# ═══════════════════════════════════════════════════════════════════════════

_FILTER_LEVELS = ("none", "standard", "aggressive")
_BROWSER_BLOCK_STATUSES = frozenset({403, 429, 503})
_BROWSER_BLOCK_MARKERS = (
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


class WebFetchTool(Tool):
    """Fetch and extract content from a URL using Readability."""

    _NAME = "web_fetch"
    _DESCRIPTION = "Fetch a URL and extract readable content as markdown or text."
    _PARAMETERS: dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "extractMode": {"type": "string", "enum": ["markdown", "text"], "default": "markdown"},
            "maxChars": {"type": "integer", "minimum": 100},
            "filterLevel": {
                "type": "string",
                "enum": ["none", "standard", "aggressive"],
                "default": "none",
                "description": (
                    "Content filter intensity. "
                    "'none': raw Readability output (default, backward compatible). "
                    "'standard': removes boilerplate lines + deduplicates adjacent paragraphs. "
                    "'aggressive': also removes link-heavy navigation paragraphs."
                ),
            },
        },
        "required": ["url"],
    }

    @property
    def name(self) -> str:
        return self._NAME

    @property
    def description(self) -> str:
        return self._DESCRIPTION

    @property
    def parameters(self) -> dict[str, Any]:
        return self._PARAMETERS

    def __init__(
        self,
        max_chars: int = 50000,
        proxy: str | None = None,
        *,
        workspace: Path | None = None,
        allowed_dir: Path | None = None,
    ):
        self.max_chars = max_chars
        self.proxy = (proxy or "").strip() or None
        self._browser_runner = (
            AgentBrowserRunner(workspace=workspace, allowed_dir=allowed_dir)
            if workspace is not None
            else None
        )

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        if self._browser_runner is not None:
            self._browser_runner.set_context(channel, chat_id, session_key)

    async def execute(self, **kwargs: Any) -> str:
        from readability import Document

        unexpected = sorted(set(kwargs) - {"url", "extractMode", "maxChars", "filterLevel"})
        if unexpected:
            return json.dumps(
                {
                    "error": f"Unexpected parameter(s): {', '.join(unexpected)}",
                    "url": _mask_url_credentials(str(kwargs.get("url", ""))),
                },
                ensure_ascii=False,
            )

        url_raw = kwargs.get("url", "")
        url = url_raw if isinstance(url_raw, str) else str(url_raw)
        masked_url = _mask_url_credentials(url)

        extract_mode_raw = kwargs.get("extractMode", "markdown")
        if not isinstance(extract_mode_raw, str):
            return json.dumps(
                {"error": "Invalid parameter 'extractMode': must be string", "url": masked_url},
                ensure_ascii=False,
            )
        extract_mode = extract_mode_raw.strip().lower()
        if extract_mode not in ("markdown", "text"):
            return json.dumps(
                {
                    "error": "Invalid parameter 'extractMode': must be one of [markdown, text]",
                    "url": masked_url,
                },
                ensure_ascii=False,
            )

        max_chars_raw = kwargs.get("maxChars")
        if isinstance(max_chars_raw, bool) or (
            max_chars_raw is not None and not isinstance(max_chars_raw, int)
        ):
            return json.dumps(
                {"error": "Invalid parameter 'maxChars': must be integer", "url": masked_url},
                ensure_ascii=False,
            )
        if isinstance(max_chars_raw, int) and max_chars_raw < 100:
            return json.dumps(
                {"error": "Invalid parameter 'maxChars': must be >= 100", "url": masked_url},
                ensure_ascii=False,
            )
        max_chars_arg = max_chars_raw if isinstance(max_chars_raw, int) else None

        filter_level_raw = kwargs.get("filterLevel", "none")
        if not isinstance(filter_level_raw, str):
            return json.dumps(
                {"error": "Invalid parameter 'filterLevel': must be string", "url": masked_url},
                ensure_ascii=False,
            )
        filter_level = filter_level_raw.strip().lower()
        if filter_level not in _FILTER_LEVELS:
            return json.dumps(
                {
                    "error": (
                        "Invalid parameter 'filterLevel': "
                        "must be one of [none, standard, aggressive]"
                    ),
                    "url": masked_url,
                },
                ensure_ascii=False,
            )

        max_chars = max_chars_arg or self.max_chars

        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps(
                {"error": f"URL validation failed: {error_msg}", "url": masked_url},
                ensure_ascii=False,
            )

        try:
            logger.debug("WebFetch: {}", "proxy enabled" if self.proxy else "direct connection")
            async with _make_async_client(
                self.proxy,
                follow_redirects=True,
                max_redirects=MAX_REDIRECTS,
                timeout=30.0,
            ) as client:
                r = await client.get(url, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()

            ctype = r.headers.get("content-type", "")
            filtered = False

            if "application/json" in ctype:
                text, extractor = json.dumps(r.json(), indent=2, ensure_ascii=False), "json"
            elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
                raw_html = r.text
                text, filtered, truncated = self._extract_readable_text(
                    raw_html=raw_html,
                    extract_mode=extract_mode,
                    filter_level=filter_level,
                    max_chars=max_chars,
                    document_cls=Document,
                )
                extractor = "readability"
                fallback_reason = self._browser_fallback_reason(
                    status=r.status_code,
                    raw_html=raw_html,
                    extracted_text=text,
                )
                fallback_payload = await self._browser_fallback_payload(
                    url=url,
                    masked_url=masked_url,
                    extract_mode=extract_mode,
                    filter_level=filter_level,
                    max_chars=max_chars,
                    fallback_reason=fallback_reason,
                )
                if fallback_payload is not None:
                    return json.dumps(fallback_payload, ensure_ascii=False)
            else:
                text, extractor = r.text, "raw"

            if extractor != "readability":
                text, truncated = self._truncate_output(text, filter_level, max_chars)

            return json.dumps(
                self._build_success_payload(
                    masked_url=masked_url,
                    final_url=str(r.url),
                    status=r.status_code,
                    extractor=extractor,
                    backend="http",
                    fallback_reason=None,
                    filter_level=filter_level,
                    filtered=filtered,
                    truncated=truncated,
                    text=text,
                ),
                ensure_ascii=False,
            )
        except httpx.ProxyError as e:
            safe = _safe_error_text(e)
            logger.error("WebFetch proxy error for {}: {}", masked_url, safe)
            return json.dumps(
                {"error": f"Proxy error: {safe}", "url": masked_url}, ensure_ascii=False
            )
        except httpx.HTTPStatusError as e:
            fallback_reason = self._browser_fallback_reason(
                status=e.response.status_code if e.response is not None else None,
                raw_html=e.response.text if e.response is not None else "",
                extracted_text="",
                error_text=_safe_error_text(e),
            )
            fallback_payload = await self._browser_fallback_payload(
                url=url,
                masked_url=masked_url,
                extract_mode=extract_mode,
                filter_level=filter_level,
                max_chars=max_chars,
                fallback_reason=fallback_reason,
            )
            if fallback_payload is not None:
                return json.dumps(fallback_payload, ensure_ascii=False)
            return json.dumps({"error": _safe_error_text(e), "url": masked_url}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": _safe_error_text(e), "url": masked_url}, ensure_ascii=False)

    def _extract_readable_text(
        self,
        *,
        raw_html: str,
        extract_mode: str,
        filter_level: str,
        max_chars: int,
        document_cls: Any,
    ) -> tuple[str, bool, bool]:
        html_for_readability = _preclean_html(raw_html) if filter_level != "none" else raw_html
        doc = document_cls(html_for_readability)
        summary = doc.summary()
        content = self._to_markdown(summary) if extract_mode == "markdown" else _strip_tags(summary)
        text = f"# {doc.title()}\n\n{content}" if doc.title() else content
        text, filtered = _apply_filters(text, filter_level)
        text, truncated = self._truncate_output(text, filter_level, max_chars)
        return text, filtered, truncated

    def _truncate_output(self, text: str, filter_level: str, max_chars: int) -> tuple[str, bool]:
        if filter_level != "none":
            return _smart_truncate(text, max_chars)
        truncated = len(text) > max_chars
        if truncated:
            return text[:max_chars], True
        return text, False

    def _build_success_payload(
        self,
        *,
        masked_url: str,
        final_url: str,
        status: int,
        extractor: str,
        backend: str,
        fallback_reason: str | None,
        filter_level: str,
        filtered: bool,
        truncated: bool,
        text: str,
    ) -> dict[str, Any]:
        return {
            "url": masked_url,
            "finalUrl": final_url,
            "status": status,
            "extractor": extractor,
            "backend": backend,
            "fallbackUsed": fallback_reason is not None,
            "fallbackReason": fallback_reason,
            "filterLevel": filter_level,
            "filtered": filtered,
            "truncated": truncated,
            "length": len(text),
            "text": text,
        }

    def _browser_fallback_reason(
        self,
        *,
        status: int | None,
        raw_html: str,
        extracted_text: str,
        error_text: str = "",
    ) -> str | None:
        if not self._browser_runner or not agent_browser_available():
            return None
        if isinstance(status, int) and status in _BROWSER_BLOCK_STATUSES:
            return f"status_{status}"
        normalized_html = raw_html.lower()
        if any(marker in normalized_html for marker in _BROWSER_BLOCK_MARKERS):
            return "challenge_detected"
        if error_text and any(marker in error_text.lower() for marker in _BROWSER_BLOCK_MARKERS):
            return "challenge_error"
        if raw_html and len(extracted_text.strip()) < 80 and len(raw_html) > 1200:
            return "empty_readability_result"
        return None

    async def _browser_fallback_payload(
        self,
        *,
        url: str,
        masked_url: str,
        extract_mode: str,
        filter_level: str,
        max_chars: int,
        fallback_reason: str | None,
    ) -> dict[str, Any] | None:
        if self._browser_runner is None or fallback_reason is None:
            return None
        logger.info("WebFetch fallback via agent-browser for {} ({})", masked_url, fallback_reason)
        fetched = await self._browser_runner.fetch_html(url, session=None)
        if error := fetched.get("error"):
            return {
                "error": f"HTTP fetch failed and browser fallback also failed: {error}",
                "url": masked_url,
            }

        from readability import Document

        text, filtered, truncated = self._extract_readable_text(
            raw_html=fetched.get("html", ""),
            extract_mode=extract_mode,
            filter_level=filter_level,
            max_chars=max_chars,
            document_cls=Document,
        )
        return self._build_success_payload(
            masked_url=masked_url,
            final_url=fetched.get("final_url", url),
            status=200,
            extractor="readability",
            backend="agent-browser",
            fallback_reason=fallback_reason,
            filter_level=filter_level,
            filtered=filtered,
            truncated=truncated,
            text=text,
        )

    def _to_markdown(self, html_content: str) -> str:
        """Convert HTML to markdown."""
        text = re.sub(
            r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
            lambda m: f"[{_strip_tags(m[2])}]({m[1]})",
            html_content,
            flags=re.I,
        )
        text = re.sub(
            r"<h([1-6])[^>]*>([\s\S]*?)</h\1>",
            lambda m: f"\n{'#' * int(m[1])} {_strip_tags(m[2])}\n",
            text,
            flags=re.I,
        )
        text = re.sub(
            r"<li[^>]*>([\s\S]*?)</li>", lambda m: f"\n- {_strip_tags(m[1])}", text, flags=re.I
        )
        text = re.sub(r"</(p|div|section|article)>", "\n\n", text, flags=re.I)
        text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.I)
        return _normalize(_strip_tags(text))
