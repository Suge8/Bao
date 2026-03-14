import asyncio
import json
from typing import Any

import httpx

from bao.agent.tools import web as web_module
from bao.agent.tools.web import WebFetchTool, WebSearchTool
from bao.config.paths import set_runtime_config_path
from tests.browser_runtime_fixture import write_fake_browser_runtime


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

    async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        if self._capture is not None:
            self._capture["url"] = url
            self._capture["kwargs"] = kwargs
        return _FakeResponse(self._payload)


class _FetchResponse:
    def __init__(
        self,
        *,
        text: str,
        status_code: int = 200,
        content_type: str = "text/html",
        url: str = "https://example.com",
    ):
        self.text = text
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self.url = url

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", self.url)
            response = httpx.Response(self.status_code, request=request, text=self.text)
            raise httpx.HTTPStatusError("boom", request=request, response=response)

    def json(self) -> dict[str, Any]:
        return json.loads(self.text)


class _FetchClient:
    def __init__(self, response: _FetchResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    async def get(self, url: str, **kwargs: Any) -> _FetchResponse:
        del url, kwargs
        return self._response


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


def test_web_fetch_falls_back_to_agent_browser_on_block(monkeypatch, tmp_path) -> None:
    runtime_root = write_fake_browser_runtime(tmp_path)
    monkeypatch.setenv("BAO_BROWSER_RUNTIME_ROOT", str(runtime_root))
    set_runtime_config_path(tmp_path / "config.jsonc")
    response = _FetchResponse(text="<html><title>Just a moment...</title></html>")
    monkeypatch.setattr(
        "bao.agent.tools.web._make_async_client", lambda *args, **kwargs: _FetchClient(response)
    )

    async def fake_fetch_html(self, url: str, *, wait_ms: int = 1500, session: str | None = None):
        del self, wait_ms, session
        return {
            "html": "<html><body><main><h1>Loaded</h1><p>Real content</p></main></body></html>",
            "final_url": url,
        }

    monkeypatch.setattr("bao.browser.runtime.BrowserAutomationService.fetch_html", fake_fetch_html)
    try:
        out = asyncio.run(
            WebFetchTool(workspace=tmp_path, allowed_dir=tmp_path).execute(
                url="https://example.com"
            )
        )
    finally:
        set_runtime_config_path(None)
    payload = json.loads(out)
    assert payload["backend"] == "agent-browser"
    assert payload["fallbackUsed"] is True
    assert payload["fallbackReason"] == "challenge_detected"
    assert "Real content" in payload["text"]


def test_web_fetch_reports_browser_fallback_failure(monkeypatch, tmp_path) -> None:
    runtime_root = write_fake_browser_runtime(tmp_path)
    monkeypatch.setenv("BAO_BROWSER_RUNTIME_ROOT", str(runtime_root))
    set_runtime_config_path(tmp_path / "config.jsonc")
    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(403, request=request, text="forbidden")

    class _StatusClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        async def get(self, url: str, **kwargs: Any):
            del url, kwargs
            raise httpx.HTTPStatusError("forbidden", request=request, response=response)

    monkeypatch.setattr(
        "bao.agent.tools.web._make_async_client", lambda *args, **kwargs: _StatusClient()
    )

    async def fake_fetch_html(self, url: str, *, wait_ms: int = 1500, session: str | None = None):
        del self, url, wait_ms, session
        return {"error": "Error: browser failed"}

    monkeypatch.setattr("bao.browser.runtime.BrowserAutomationService.fetch_html", fake_fetch_html)
    try:
        out = asyncio.run(
            WebFetchTool(workspace=tmp_path, allowed_dir=tmp_path).execute(
                url="https://example.com"
            )
        )
    finally:
        set_runtime_config_path(None)
    payload = json.loads(out)
    assert payload["error"].startswith("HTTP fetch failed and browser fallback also failed")


def test_mask_url_credentials_redacts_userinfo() -> None:
    text = "proxy http://alice:secret@proxy.example:8080 refused"
    masked = web_module._mask_url_credentials(text)
    assert "alice:secret@" not in masked
    assert "***:***@proxy.example:8080" in masked


def test_make_async_client_falls_back_to_proxies(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

    def _fake_async_client(*args: Any, **kwargs: Any):
        del args
        if "proxy" in kwargs:
            raise TypeError("unexpected keyword argument 'proxy'")
        captured.update(kwargs)
        return _Client()

    monkeypatch.setattr("bao.agent.tools.web.httpx.AsyncClient", _fake_async_client)

    client = web_module._make_async_client("http://user:pass@proxy.local:7890", timeout=5.0)

    assert isinstance(client, _Client)
    assert captured["proxies"]["http://"] == "http://user:pass@proxy.local:7890"
    assert captured["proxies"]["https://"] == "http://user:pass@proxy.local:7890"


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


def test_web_fetch_proxy_error_redacts_credentials(monkeypatch) -> None:
    class _ProxyFailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        async def get(self, *args: Any, **kwargs: Any):
            del args, kwargs
            raise httpx.ProxyError("proxy socks5://alice:secret@127.0.0.1:1080 failed")

    monkeypatch.setattr(
        "bao.agent.tools.web.httpx.AsyncClient", lambda *args, **kwargs: _ProxyFailClient()
    )

    out = asyncio.run(
        WebFetchTool(proxy="socks5://alice:secret@127.0.0.1:1080").execute(
            url="https://example.com"
        )
    )
    payload = json.loads(out)

    assert payload["error"].startswith("Proxy error:")
    assert "alice:secret@" not in payload["error"]
    assert "***:***@127.0.0.1:1080" in payload["error"]


def test_web_fetch_masks_credentials_in_url_field(monkeypatch) -> None:
    class _ProxyFailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        async def get(self, *args: Any, **kwargs: Any):
            del args, kwargs
            raise httpx.ProxyError("proxy failed")

    monkeypatch.setattr(
        "bao.agent.tools.web.httpx.AsyncClient", lambda *args, **kwargs: _ProxyFailClient()
    )

    out = asyncio.run(WebFetchTool().execute(url="https://alice:secret@example.com/private"))
    payload = json.loads(out)

    assert payload["url"] == "https://***:***@example.com/private"
