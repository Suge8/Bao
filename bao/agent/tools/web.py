"""Web tools: web_search and web_fetch."""

import html
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from bao.agent.tools.base import Tool

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5


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

    name = "web_search"
    description = "Search the web using Tavily/Brave/Exa API. ALWAYS use this instead of exec+curl or web_fetch when you need to find information, news, or answers. Returns structured titles, URLs, and snippets."
    parameters = {
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

    def __init__(self, search_config: "WebSearchConfig | None" = None):
        self.provider = search_config.provider if search_config else ""
        self.brave_key = (search_config.brave_api_key if search_config else None) or os.environ.get(
            "BRAVE_API_KEY", ""
        )
        self.tavily_key = (
            search_config.tavily_api_key if search_config else None
        ) or os.environ.get("TAVILY_API_KEY", "")
        self.max_results = search_config.max_results if search_config else 5
        self.exa_key = (search_config.exa_api_key if search_config else None) or os.environ.get(
            "EXA_API_KEY", ""
        )

    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
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
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers={"Accept": "application/json", "X-Subscription-Token": self.brave_key},
                    timeout=10.0,
                )
                r.raise_for_status()
            results = r.json().get("web", {}).get("results", [])
            return self._format(query, results, n)
        except Exception as e:
            return f"Error: {e}"

    async def _tavily(self, query: str, n: int) -> str:
        try:
            async with httpx.AsyncClient() as client:
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
                out = f"AI Answer: {answer}\n\n{out}"
            return out
        except Exception as e:
            return f"Error: {e}"

    async def _exa(self, query: str, n: int) -> str:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://api.exa.ai/search",
                    json={"query": query, "numResults": n, "contents": {"text": {"maxCharacters": 300}}},
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
        except Exception as e:
            return f"Error: {e}"

    @staticmethod
    def _format(query: str, results: list[dict], n: int) -> str:
        if not results:
            return f"No results for: {query}"
        lines = [f"Results for: {query}\n"]
        for i, item in enumerate(results[:n], 1):
            lines.append(f"{i}. {item.get('title', '')}\n   {item.get('url', '')}")
            if desc := item.get("description"):
                lines.append(f"   {desc}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# WebFetchTool
# ═══════════════════════════════════════════════════════════════════════════

_FILTER_LEVELS = ("none", "standard", "aggressive")


class WebFetchTool(Tool):
    """Fetch and extract content from a URL using Readability."""

    name = "web_fetch"
    description = (
        "Fetch URL and extract readable content (HTML → markdown/text). "
        "Use filterLevel='standard' for cleaner output (removes boilerplate, deduplicates); "
        "'aggressive' also strips link-heavy navigation paragraphs."
    )
    parameters = {
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

    def __init__(self, max_chars: int = 50000):
        self.max_chars = max_chars

    async def execute(
        self,
        url: str,
        extractMode: str = "markdown",
        maxChars: int | None = None,
        filterLevel: str = "none",
        **kwargs: Any,
    ) -> str:
        from readability import Document

        max_chars = maxChars or self.max_chars
        if filterLevel not in _FILTER_LEVELS:
            filterLevel = "none"

        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps(
                {"error": f"URL validation failed: {error_msg}", "url": url}, ensure_ascii=False
            )

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, max_redirects=MAX_REDIRECTS, timeout=30.0
            ) as client:
                r = await client.get(url, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()

            ctype = r.headers.get("content-type", "")
            filtered = False

            if "application/json" in ctype:
                text, extractor = json.dumps(r.json(), indent=2, ensure_ascii=False), "json"
            elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
                raw_html = r.text
                if filterLevel != "none":
                    raw_html = _preclean_html(raw_html)

                doc = Document(raw_html)
                summary = doc.summary()
                content = (
                    self._to_markdown(summary)
                    if extractMode == "markdown"
                    else _strip_tags(summary)
                )
                text = f"# {doc.title()}\n\n{content}" if doc.title() else content
                extractor = "readability"
                text, filtered = _apply_filters(text, filterLevel)
            else:
                text, extractor = r.text, "raw"

            if filterLevel != "none":
                text, truncated = _smart_truncate(text, max_chars)
            else:
                truncated = len(text) > max_chars
                if truncated:
                    text = text[:max_chars]

            return json.dumps(
                {
                    "url": url,
                    "finalUrl": str(r.url),
                    "status": r.status_code,
                    "extractor": extractor,
                    "filterLevel": filterLevel,
                    "filtered": filtered,
                    "truncated": truncated,
                    "length": len(text),
                    "text": text,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)

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
