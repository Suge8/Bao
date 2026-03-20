from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from bao.agent.tools._web_common import resolve_search_config
from bao.agent.tools.base import Tool


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

    def __init__(self, search_config: Any | None = None, proxy: str | None = None):
        resolved = resolve_search_config(search_config, proxy)
        self.provider = resolved["provider"]
        self.brave_key = resolved["brave_key"]
        self.tavily_key = resolved["tavily_key"]
        self.max_results = resolved["max_results"]
        self.exa_key = resolved["exa_key"]
        self.exa_max_characters = resolved["exa_max_characters"]
        self.proxy = resolved["proxy"]

    async def execute(self, **kwargs: Any) -> str:
        unexpected = sorted(set(kwargs) - {"query", "count"})
        if unexpected:
            return f"Error: Unexpected parameter(s): {', '.join(unexpected)}"

        query_raw = kwargs.get("query", "")
        query = query_raw if isinstance(query_raw, str) else str(query_raw)
        if not query.strip():
            return "Error: Missing required parameter 'query'"

        count_raw = kwargs.get("count")
        if isinstance(count_raw, bool) or (count_raw is not None and not isinstance(count_raw, int)):
            return "Error: Invalid parameter 'count': must be integer"
        count = count_raw if isinstance(count_raw, int) else None

        n = min(max(count or self.max_results, 1), 10)
        provider_name = (self.provider or "").lower()
        dispatch = {"tavily": self._tavily, "brave": self._brave, "exa": self._exa}
        keys = {"tavily": self.tavily_key, "brave": self.brave_key, "exa": self.exa_key}
        default_order = [name for name in ("tavily", "brave", "exa") if keys.get(name)]
        order = [provider_name] + [name for name in default_order if name != provider_name] if provider_name in dispatch and keys.get(provider_name) else default_order
        for provider in order:
            result = await dispatch[provider](query, n)
            if not result.startswith("Error:"):
                return result
        return "Error: No search API key configured (set provider + API key in config)"

    async def _brave(self, query: str, n: int) -> str:
        from bao.agent.tools import web as web_module

        try:
            logger.debug("WebSearch: {}", "proxy enabled" if self.proxy else "direct connection")
            async with web_module._make_async_client(self.proxy) as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers={"Accept": "application/json", "X-Subscription-Token": self.brave_key},
                    timeout=10.0,
                )
                response.raise_for_status()
            results = response.json().get("web", {}).get("results", [])[:n]
            return self._format(query, results, n)
        except httpx.ProxyError as exc:
            safe = web_module._safe_error_text(exc)
            logger.error("WebSearch proxy error: {}", safe)
            return f"Error: Proxy error: {safe}"
        except Exception as exc:
            return f"Error: {web_module._safe_error_text(exc)}"

    async def _tavily(self, query: str, n: int) -> str:
        from bao.agent.tools import web as web_module

        try:
            logger.debug("WebSearch: {}", "proxy enabled" if self.proxy else "direct connection")
            async with web_module._make_async_client(self.proxy) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.tavily_key,
                        "query": query,
                        "max_results": n,
                        "include_answer": True,
                    },
                    timeout=15.0,
                )
                response.raise_for_status()
            data = response.json()
            results = [
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("content", ""),
                }
                for item in data.get("results", [])
            ]
            answer = data.get("answer", "")
            output = self._format(query, results, n)
            if answer:
                output = f"[AI Summary] {answer}\n\n---\n\n{output}"
            return output
        except httpx.ProxyError as exc:
            safe = web_module._safe_error_text(exc)
            logger.error("WebSearch proxy error: {}", safe)
            return f"Error: Proxy error: {safe}"
        except Exception as exc:
            return f"Error: {web_module._safe_error_text(exc)}"

    async def _exa(self, query: str, n: int) -> str:
        from bao.agent.tools import web as web_module

        try:
            logger.debug("WebSearch: {}", "proxy enabled" if self.proxy else "direct connection")
            async with web_module._make_async_client(self.proxy) as client:
                response = await client.post(
                    "https://api.exa.ai/search",
                    json={
                        "query": query,
                        "numResults": n,
                        "contents": {"text": {"maxCharacters": self.exa_max_characters}},
                    },
                    headers={"x-api-key": self.exa_key, "Content-Type": "application/json"},
                    timeout=15.0,
                )
                response.raise_for_status()
            data = response.json()
            results = [
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("text", ""),
                }
                for item in data.get("results", [])
            ]
            return self._format(query, results, n)
        except httpx.ProxyError as exc:
            safe = web_module._safe_error_text(exc)
            logger.error("WebSearch proxy error: {}", safe)
            return f"Error: Proxy error: {safe}"
        except Exception as exc:
            return f"Error: {web_module._safe_error_text(exc)}"

    @staticmethod
    def _format(query: str, results: list[dict[str, str]], n: int) -> str:
        if not results:
            return f"No results for: {query}"
        lines = [f"Results for: {query}\n"]
        for index, item in enumerate(results[:n], 1):
            lines.append(f"[{index}] {item.get('title', '')}\n   {item.get('url', '')}")
            if desc := item.get("description"):
                lines.append(f"   {desc}")
            lines.append("")
        return "\n".join(lines).rstrip()
