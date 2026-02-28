import asyncio
import json
from typing import Any

from bao.agent.tools.web import WebFetchTool, WebSearchTool


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict[str, Any], capture: dict[str, Any] | None = None):
        self._payload = payload
        self._capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        if self._capture is not None:
            self._capture["url"] = url
            self._capture["kwargs"] = kwargs
        return _FakeResponse(self._payload)


async def _provider_error(query: str, n: int) -> str:
    del query, n
    return "Error: upstream provider unavailable"


async def _provider_ok(query: str, n: int) -> str:
    return f"Results for: {query} ({n})"


def test_format_uses_bracketed_citations_with_spacing() -> None:
    out = WebSearchTool._format(
        "python",
        [
            {"title": "First", "url": "https://a.example", "description": "desc-a"},
            {"title": "Second", "url": "https://b.example", "description": "desc-b"},
        ],
        2,
    )

    assert "[1] First" in out
    assert "\n\n[2] Second" in out
    assert "1. First" not in out


def test_tavily_answer_is_labeled_and_separated(monkeypatch) -> None:
    payload = {
        "answer": "direct answer",
        "results": [{"title": "Title", "url": "https://a.example", "content": "snippet"}],
    }
    monkeypatch.setattr(
        "bao.agent.tools.web.httpx.AsyncClient",
        lambda: _FakeClient(payload),
    )

    out = asyncio.run(WebSearchTool()._tavily("query", 1))

    assert out.startswith("[AI Summary] direct answer")
    assert "\n\n---\n\nResults for: query" in out


def test_exa_uses_higher_max_characters(monkeypatch) -> None:
    capture: dict[str, Any] = {}
    payload = {"results": []}
    monkeypatch.setattr(
        "bao.agent.tools.web.httpx.AsyncClient",
        lambda: _FakeClient(payload, capture),
    )

    _ = asyncio.run(WebSearchTool()._exa("query", 2))

    assert capture["url"] == "https://api.exa.ai/search"
    assert capture["kwargs"]["json"]["contents"]["text"]["maxCharacters"] == 1000


def test_execute_fallbacks_to_next_provider_on_error() -> None:
    tool = WebSearchTool()
    tool.provider = "tavily"
    tool.tavily_key = "tv"
    tool.brave_key = "br"
    tool.exa_key = ""
    tool._tavily = _provider_error
    tool._brave = _provider_ok

    out = asyncio.run(tool.execute(query="fallback", count=2))

    assert out == "Results for: fallback (2)"


def test_execute_rejects_unexpected_parameters() -> None:
    out = asyncio.run(WebSearchTool().execute(query="hello", n=3))
    assert out.startswith("Error: Unexpected parameter(s):")


def test_execute_rejects_bool_count_parameter() -> None:
    out = asyncio.run(WebSearchTool().execute(query="hello", count=True))
    assert out == "Error: Invalid parameter 'count': must be integer"


def test_web_fetch_rejects_unexpected_parameters() -> None:
    out = asyncio.run(WebFetchTool().execute(url="https://example.com", max_chars=100))
    payload = json.loads(out)
    assert payload["error"].startswith("Unexpected parameter(s):")


def test_web_fetch_rejects_invalid_extract_mode() -> None:
    out = asyncio.run(WebFetchTool().execute(url="https://example.com", extractMode="md"))
    payload = json.loads(out)
    assert payload["error"].startswith("Invalid parameter 'extractMode'")


def test_web_fetch_rejects_invalid_filter_level() -> None:
    out = asyncio.run(WebFetchTool().execute(url="https://example.com", filterLevel="fast"))
    payload = json.loads(out)
    assert payload["error"].startswith("Invalid parameter 'filterLevel'")


def test_web_fetch_rejects_non_integer_max_chars() -> None:
    out = asyncio.run(WebFetchTool().execute(url="https://example.com", maxChars="500"))
    payload = json.loads(out)
    assert payload["error"] == "Invalid parameter 'maxChars': must be integer"
