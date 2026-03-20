from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from bao.agent.tools._web_fetch_support import SuccessPayloadRequest, build_success_payload


@dataclass(slots=True)
class FetchExecutionRequest:
    url: str
    masked_url: str
    extract_mode: str
    filter_level: str
    max_chars: int


@dataclass(slots=True)
class BrowserFallbackRequest:
    url: str
    masked_url: str
    extract_mode: str
    filter_level: str
    max_chars: int
    fallback_reason: str | None


@dataclass(slots=True)
class SuccessPayloadBuildRequest:
    request: FetchExecutionRequest
    final_url: str
    status: int
    extractor: str
    backend: str
    fallback_reason: str | None
    filtered: bool
    truncated: bool
    text: str


@dataclass(slots=True)
class HttpSuccessPayloadRequest:
    tool: Any
    response: httpx.Response
    request: FetchExecutionRequest
    document_cls: Any
    truncate_output: Any
    browser_fallback_reason: Any


@dataclass(slots=True)
class HtmlPayloadRequest:
    tool: Any
    response: httpx.Response
    raw_html: str
    request: FetchExecutionRequest
    document_cls: Any
    browser_fallback_reason: Any


def build_success_payload_for_request(request: SuccessPayloadBuildRequest) -> dict[str, Any]:
    fetch_request = request.request
    return build_success_payload(
        SuccessPayloadRequest(
            masked_url=fetch_request.masked_url,
            final_url=request.final_url,
            status=request.status,
            extractor=request.extractor,
            backend=request.backend,
            fallback_reason=request.fallback_reason,
            filter_level=fetch_request.filter_level,
            filtered=request.filtered,
            truncated=request.truncated,
            text=request.text,
        )
    )


def build_execution_request(
    kwargs: dict[str, Any],
    *,
    masked_url: str,
    default_max_chars: int,
    parse_fetch_request: Any,
) -> tuple[FetchExecutionRequest | None, dict[str, Any] | None]:
    unexpected = sorted(set(kwargs) - {"url", "extractMode", "maxChars", "filterLevel"})
    if unexpected:
        return None, {
            "error": f"Unexpected parameter(s): {', '.join(unexpected)}",
            "url": masked_url,
        }
    parsed_request = parse_fetch_request(
        kwargs,
        masked_url=masked_url,
        default_max_chars=default_max_chars,
    )
    if "error" in parsed_request:
        return None, parsed_request
    url_raw = kwargs.get("url", "")
    url = url_raw if isinstance(url_raw, str) else str(url_raw)
    return (
        FetchExecutionRequest(
            url=url,
            masked_url=masked_url,
            extract_mode=str(parsed_request["extract_mode"]),
            filter_level=str(parsed_request["filter_level"]),
            max_chars=int(parsed_request["max_chars"]),
        ),
        None,
    )


async def build_http_success_payload(request: HttpSuccessPayloadRequest) -> dict[str, Any]:
    response = request.response
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        text = json.dumps(response.json(), indent=2, ensure_ascii=False)
        text, truncated = request.truncate_output(
            text,
            request.request.filter_level,
            request.request.max_chars,
        )
        return build_success_payload_for_request(
            SuccessPayloadBuildRequest(
                request=request.request,
                final_url=str(response.url),
                status=response.status_code,
                extractor="json",
                backend="http",
                fallback_reason=None,
                filtered=False,
                truncated=truncated,
                text=text,
            )
        )
    if "text/html" in content_type or response.text[:256].lower().startswith(("<!doctype", "<html")):
        return await extract_html_payload(
            HtmlPayloadRequest(
                tool=request.tool,
                response=response,
                raw_html=response.text,
                request=request.request,
                document_cls=request.document_cls,
                browser_fallback_reason=request.browser_fallback_reason,
            )
        )
    text, truncated = request.truncate_output(
        response.text,
        request.request.filter_level,
        request.request.max_chars,
    )
    return build_success_payload_for_request(
        SuccessPayloadBuildRequest(
            request=request.request,
            final_url=str(response.url),
            status=response.status_code,
            extractor="raw",
            backend="http",
            fallback_reason=None,
            filtered=False,
            truncated=truncated,
            text=text,
        )
    )


async def extract_html_payload(request: HtmlPayloadRequest) -> dict[str, Any]:
    text, filtered, truncated = request.tool._extract_readable_text(
        raw_html=request.raw_html,
        extract_mode=request.request.extract_mode,
        filter_level=request.request.filter_level,
        max_chars=request.request.max_chars,
        document_cls=request.document_cls,
    )
    fallback_reason = request.browser_fallback_reason(
        browser_available=bool(
            request.tool._browser_service is not None and request.tool._browser_service.available
        ),
        status=request.response.status_code,
        raw_html=request.raw_html,
        extracted_text=text,
    )
    fallback_payload = await request.tool._browser_fallback_payload(
        BrowserFallbackRequest(
            url=request.request.url,
            masked_url=request.request.masked_url,
            extract_mode=request.request.extract_mode,
            filter_level=request.request.filter_level,
            max_chars=request.request.max_chars,
            fallback_reason=fallback_reason,
        )
    )
    if fallback_payload is not None:
        return fallback_payload
    return build_success_payload_for_request(
        SuccessPayloadBuildRequest(
            request=request.request,
            final_url=str(request.response.url),
            status=request.response.status_code,
            extractor="readability",
            backend="http",
            fallback_reason=None,
            filtered=filtered,
            truncated=truncated,
            text=text,
        )
    )
