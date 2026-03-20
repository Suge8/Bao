from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from bao.agent.tools._web_common import (
    MAX_REDIRECTS,
    USER_AGENT,
    strip_tags,
)
from bao.agent.tools._web_fetch_runtime import (
    BrowserFallbackRequest,
    FetchExecutionRequest,
    HttpSuccessPayloadRequest,
    SuccessPayloadBuildRequest,
    build_execution_request,
    build_http_success_payload,
    build_success_payload_for_request,
)
from bao.agent.tools._web_fetch_support import (
    browser_fallback_reason,
    parse_fetch_request,
    truncate_output,
)
from bao.agent.tools._web_filters import (
    apply_filters,
    html_to_markdown,
    preclean_html,
)
from bao.agent.tools.base import Tool
from bao.browser import BrowserAutomationOptions, BrowserAutomationService


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
        browser_enabled: bool = True,
        allowed_dir: Path | None = None,
    ):
        self.max_chars = max_chars
        self.proxy = (proxy or "").strip() or None
        self._browser_service = (
            BrowserAutomationService(
                workspace,
                BrowserAutomationOptions(enabled=browser_enabled, allowed_dir=allowed_dir),
            )
            if workspace is not None
            else None
        )

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        if self._browser_service is not None:
            self._browser_service.set_context(channel, chat_id, session_key)

    async def execute(self, **kwargs: Any) -> str:
        from readability import Document

        from bao.agent.tools import web as web_module

        url_raw = kwargs.get("url", "")
        url = url_raw if isinstance(url_raw, str) else str(url_raw)
        masked_url = web_module._mask_url_credentials(url)
        request, error_payload = build_execution_request(
            kwargs,
            masked_url=masked_url,
            default_max_chars=self.max_chars,
            parse_fetch_request=parse_fetch_request,
        )
        if error_payload is not None:
            return json.dumps(error_payload, ensure_ascii=False)
        assert request is not None
        is_valid, error_msg = web_module._validate_url(request.url)
        if not is_valid:
            return self._json_error(
                masked_url=request.masked_url,
                message=f"URL validation failed: {error_msg}",
            )

        try:
            response = await self._fetch_http_response(request.url, web_module)
            payload = await build_http_success_payload(
                HttpSuccessPayloadRequest(
                    tool=self,
                    response=response,
                    request=request,
                    document_cls=Document,
                    truncate_output=truncate_output,
                    browser_fallback_reason=browser_fallback_reason,
                )
            )
            return json.dumps(payload, ensure_ascii=False)
        except httpx.ProxyError as exc:
            safe = web_module._safe_error_text(exc)
            logger.error("WebFetch proxy error for {}: {}", request.masked_url, safe)
            return self._json_error(
                masked_url=request.masked_url,
                message=f"Proxy error: {safe}",
            )
        except httpx.HTTPStatusError as exc:
            return await self._handle_http_status_error(
                request=request,
                exc=exc,
                safe_error=web_module._safe_error_text(exc),
            )
        except Exception as exc:
            return self._json_error(
                masked_url=request.masked_url,
                message=web_module._safe_error_text(exc),
            )

    @staticmethod
    def _json_error(*, masked_url: str, message: str) -> str:
        return json.dumps({"error": message, "url": masked_url}, ensure_ascii=False)

    async def _fetch_http_response(self, url: str, web_module: Any) -> httpx.Response:
        logger.debug("WebFetch: {}", "proxy enabled" if self.proxy else "direct connection")
        async with web_module._make_async_client(
            self.proxy,
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            timeout=30.0,
        ) as client:
            response = await client.get(url, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            return response

    def _extract_readable_text(
        self,
        *,
        raw_html: str,
        extract_mode: str,
        filter_level: str,
        max_chars: int,
        document_cls: Any,
    ) -> tuple[str, bool, bool]:
        html_for_readability = preclean_html(raw_html) if filter_level != "none" else raw_html
        doc = document_cls(html_for_readability)
        summary = doc.summary()
        content = html_to_markdown(summary) if extract_mode == "markdown" else strip_tags(summary)
        text = f"# {doc.title()}\n\n{content}" if doc.title() else content
        text, filtered = apply_filters(text, filter_level)
        text, truncated = truncate_output(text, filter_level, max_chars)
        return text, filtered, truncated

    async def _handle_http_status_error(
        self,
        *,
        request: FetchExecutionRequest,
        exc: httpx.HTTPStatusError,
        safe_error: str,
    ) -> str:
        fallback_reason = browser_fallback_reason(
            browser_available=bool(self._browser_service is not None and self._browser_service.available),
            status=exc.response.status_code if exc.response is not None else None,
            raw_html=exc.response.text if exc.response is not None else "",
            extracted_text="",
            error_text=safe_error,
        )
        fallback_payload = await self._browser_fallback_payload(
            BrowserFallbackRequest(
                url=request.url,
                masked_url=request.masked_url,
                extract_mode=request.extract_mode,
                filter_level=request.filter_level,
                max_chars=request.max_chars,
                fallback_reason=fallback_reason,
            )
        )
        if fallback_payload is not None:
            return json.dumps(fallback_payload, ensure_ascii=False)
        return self._json_error(masked_url=request.masked_url, message=safe_error)

    async def _browser_fallback_payload(
        self,
        request: BrowserFallbackRequest,
    ) -> dict[str, Any] | None:
        if self._browser_service is None or request.fallback_reason is None:
            return None
        logger.info(
            "WebFetch fallback via agent-browser for {} ({})",
            request.masked_url,
            request.fallback_reason,
        )
        fetched = await self._browser_service.fetch_html(request.url, session=None)
        if error := fetched.get("error"):
            return {
                "error": f"HTTP fetch failed and browser fallback also failed: {error}",
                "url": request.masked_url,
            }

        from readability import Document

        text, filtered, truncated = self._extract_readable_text(
            raw_html=fetched.get("html", ""),
            extract_mode=request.extract_mode,
            filter_level=request.filter_level,
            max_chars=request.max_chars,
            document_cls=Document,
        )
        return build_success_payload_for_request(
            SuccessPayloadBuildRequest(
                request=FetchExecutionRequest(
                    url=request.url,
                    masked_url=request.masked_url,
                    extract_mode=request.extract_mode,
                    filter_level=request.filter_level,
                    max_chars=request.max_chars,
                ),
                final_url=fetched.get("final_url", request.url),
                status=200,
                extractor="readability",
                backend="agent-browser",
                fallback_reason=request.fallback_reason,
                filtered=filtered,
                truncated=truncated,
                text=text,
            )
        )
