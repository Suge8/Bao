# ruff: noqa: F401
from __future__ import annotations

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


__all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]
