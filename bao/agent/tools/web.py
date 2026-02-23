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


class WebSearchTool(Tool):
    """Search the web using Brave or Tavily API."""

    name = "web_search"
    description = "Search the web using Tavily/Brave API. ALWAYS use this instead of exec+curl or web_fetch when you need to find information, news, or answers. Returns structured titles, URLs, and snippets."
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
        self.brave_key = (search_config.brave_api_key if search_config else None) or os.environ.get("BRAVE_API_KEY", "")
        self.tavily_key = (search_config.tavily_api_key if search_config else None) or os.environ.get("TAVILY_API_KEY", "")
        self.max_results = search_config.max_results if search_config else 5

    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        n = min(max(count or self.max_results, 1), 10)
        p = self.provider.lower()
        if p == "tavily" and self.tavily_key:
            result = await self._tavily(query, n)
            if not result.startswith("Error:") or not self.brave_key:
                return result
            return await self._brave(query, n)
        if p == "brave" and self.brave_key:
            return await self._brave(query, n)
        if self.tavily_key:
            return await self._tavily(query, n)
        if self.brave_key:
            return await self._brave(query, n)
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


class WebFetchTool(Tool):
    """Fetch and extract content from a URL using Readability."""

    name = "web_fetch"
    description = "Fetch URL and extract readable content (HTML → markdown/text)."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "extractMode": {"type": "string", "enum": ["markdown", "text"], "default": "markdown"},
            "maxChars": {"type": "integer", "minimum": 100},
        },
        "required": ["url"],
    }

    def __init__(self, max_chars: int = 50000):
        self.max_chars = max_chars

    async def execute(
        self, url: str, extractMode: str = "markdown", maxChars: int | None = None, **kwargs: Any
    ) -> str:
        from readability import Document

        max_chars = maxChars or self.max_chars

        # Validate URL before fetching
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

            # JSON
            if "application/json" in ctype:
                text, extractor = json.dumps(r.json(), indent=2, ensure_ascii=False), "json"
            # HTML
            elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
                doc = Document(r.text)
                content = (
                    self._to_markdown(doc.summary())
                    if extractMode == "markdown"
                    else _strip_tags(doc.summary())
                )
                text = f"# {doc.title()}\n\n{content}" if doc.title() else content
                extractor = "readability"
            else:
                text, extractor = r.text, "raw"

            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]

            return json.dumps(
                {
                    "url": url,
                    "finalUrl": str(r.url),
                    "status": r.status_code,
                    "extractor": extractor,
                    "truncated": truncated,
                    "length": len(text),
                    "text": text,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)

    def _to_markdown(self, html: str) -> str:
        """Convert HTML to markdown."""
        # Convert links, headings, lists before stripping tags
        text = re.sub(
            r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
            lambda m: f"[{_strip_tags(m[2])}]({m[1]})",
            html,
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
