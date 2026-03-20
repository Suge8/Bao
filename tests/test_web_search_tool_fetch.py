# ruff: noqa: F403, F405
from __future__ import annotations

from tests._web_search_tool_testkit import *


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
