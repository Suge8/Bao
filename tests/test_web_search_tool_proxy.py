# ruff: noqa: F403, F405
from __future__ import annotations

from tests._web_search_tool_testkit import *


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
