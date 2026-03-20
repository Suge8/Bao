# ruff: noqa: F403, F405
from __future__ import annotations

from tests._web_search_tool_testkit import *


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
        lambda *args, **kwargs: _FakeClient(payload),
    )

    out = asyncio.run(WebSearchTool()._tavily("query", 1))

    assert out.startswith("[AI Summary] direct answer")
    assert "\n\n---\n\nResults for: query" in out


def test_exa_uses_higher_max_characters(monkeypatch) -> None:
    capture: dict[str, Any] = {}
    payload = {"results": []}
    monkeypatch.setattr(
        "bao.agent.tools.web.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeClient(payload, capture),
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


def test_web_search_proxy_error_redacts_credentials(monkeypatch) -> None:
    class _ProxyFailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        async def get(self, *args: Any, **kwargs: Any):
            del args, kwargs
            raise httpx.ProxyError("proxy http://user:pass@proxy.local:7890 failed")

    monkeypatch.setattr(
        "bao.agent.tools.web.httpx.AsyncClient", lambda *args, **kwargs: _ProxyFailClient()
    )

    tool = WebSearchTool()
    tool.brave_key = "k"
    out = asyncio.run(tool._brave("hello", 1))

    assert out.startswith("Error: Proxy error:")
    assert "user:pass@" not in out
    assert "***:***@proxy.local:7890" in out
