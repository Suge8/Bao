"""OpenAI Codex Responses Provider."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Awaitable, Callable

import httpx
from oauth_cli_kit import get_token as get_codex_token

from bao.providers._openai_provider_common import (
    _normalize_openai_reasoning_effort,
    _normalize_service_tier,
)
from bao.providers.base import (
    ChatRequest,
    LLMProvider,
    LLMResponse,
    ProviderCapabilitySnapshot,
    ToolCallRequest,
)
from bao.providers.responses_compat import (
    append_responses_tool_call_arguments,
    build_responses_tool_call_request,
    convert_messages_to_responses,
    convert_tools_to_responses,
    replace_responses_tool_call_arguments,
    start_responses_tool_call,
)
from bao.providers.retry import emit_progress
from bao.providers.runtime import ProviderExecutionRequest, ProviderRuntimeExecutor

DEFAULT_CODEX_URL = "https://chatgpt.com/backend-api/codex/responses"
DEFAULT_ORIGINATOR = "Bao"


@dataclass(frozen=True)
class _CodexRequest:
    url: str
    headers: dict[str, str]
    body: dict[str, Any]
    verify: bool
    on_progress: Callable[[str], Awaitable[None]] | None = None


class OpenAICodexProvider(LLMProvider):
    """Use Codex OAuth to call the Responses API."""

    def __init__(self, default_model: str = "openai-codex/gpt-5.1-codex"):
        super().__init__(api_key=None, api_base=None)
        self.default_model = default_model

    def get_capability_snapshot(self, model: str | None = None) -> ProviderCapabilitySnapshot:
        del model
        return ProviderCapabilitySnapshot(
            provider_name="openai-codex",
            default_api_mode="responses",
            supported_api_modes=("responses",),
            supports_streaming=True,
            supports_tools=True,
            supports_reasoning_effort=True,
            supports_service_tier=True,
            supports_prompt_caching=True,
            supports_thinking=True,
        )

    async def chat(self, request: ChatRequest) -> LLMResponse:
        model = request.model or self.default_model
        reasoning_effort = _normalize_openai_reasoning_effort(request.reasoning_effort, allow_off=True)
        service_tier = _normalize_service_tier(request.service_tier)
        system_prompt, input_items = convert_messages_to_responses(request.messages)

        token = await asyncio.to_thread(get_codex_token)
        account_id = token.account_id or ""
        if not account_id:
            return LLMResponse(
                content="Error calling Codex: missing account id from oauth token",
                finish_reason="error",
            )
        headers = _build_headers(account_id, token.access)

        body: dict[str, Any] = {
            "model": _strip_model_prefix(model),
            "store": False,
            "stream": True,
            "instructions": system_prompt,
            "input": input_items,
            "text": {"verbosity": "medium"},
            "include": ["reasoning.encrypted_content"],
            "prompt_cache_key": _prompt_cache_key(request.messages),
        }
        if reasoning_effort:
            body["reasoning"] = {"effort": reasoning_effort}
        if service_tier:
            body["service_tier"] = service_tier

        if request.tools:
            body["tools"] = convert_tools_to_responses(request.tools)
            body["tool_choice"] = "auto"
            body["parallel_tool_calls"] = True

        url = DEFAULT_CODEX_URL
        executor = ProviderRuntimeExecutor("openai-codex")

        async def _run_once() -> LLMResponse:
            content, tool_calls, finish_reason = await _request_codex(
                _CodexRequest(
                    url=url,
                    headers=headers,
                    body=body,
                    verify=True,
                    on_progress=request.on_progress,
                )
            )
            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )

        result = await executor.run(
            _run_once,
            ProviderExecutionRequest(
                error_prefix="Error calling Codex",
                progress_error_prefix="Error calling Codex progress callback",
            ),
        )
        return result

    def get_default_model(self) -> str:
        return self.default_model


def _strip_model_prefix(model: str) -> str:
    if model.startswith("openai-codex/") or model.startswith("openai_codex/"):
        return model.split("/", 1)[1]
    return model


def _build_headers(account_id: str, token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "chatgpt-account-id": account_id,
        "OpenAI-Beta": "responses=experimental",
        "originator": DEFAULT_ORIGINATOR,
        "User-Agent": "Bao (python)",
        "accept": "text/event-stream",
        "content-type": "application/json",
    }


async def _request_codex(request: _CodexRequest) -> tuple[str, list[ToolCallRequest], str]:
    async with httpx.AsyncClient(timeout=60.0, verify=request.verify) as client:
        async with client.stream("POST", request.url, headers=request.headers, json=request.body) as response:
            if response.status_code != 200:
                text = await response.aread()
                raise RuntimeError(
                    _friendly_error(response.status_code, text.decode("utf-8", "ignore"))
                )
            return await _consume_sse(response, on_progress=request.on_progress)


def _prompt_cache_key(messages: list[dict[str, Any]]) -> str:
    raw = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _iter_sse(response: httpx.Response) -> AsyncGenerator[dict[str, Any], None]:
    buffer: list[str] = []
    async for line in response.aiter_lines():
        if line == "":
            if buffer:
                data_lines = [item[5:].strip() for item in buffer if item.startswith("data:")]
                buffer = []
                if not data_lines:
                    continue
                data = "\n".join(data_lines).strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    yield json.loads(data)
                except Exception:
                    continue
            continue
        buffer.append(line)


async def _consume_sse(
    response: httpx.Response,
    on_progress: Callable[[str], Awaitable[None]] | None = None,
) -> tuple[str, list[ToolCallRequest], str]:
    content = ""
    tool_calls: list[ToolCallRequest] = []
    tool_call_buffers: dict[str, dict[str, Any]] = {}
    finish_reason = "stop"

    async for event in _iter_sse(response):
        event_type = event.get("type")
        if event_type == "response.output_item.added":
            item = event.get("item") or {}
            start_responses_tool_call(tool_call_buffers, item)
        elif event_type == "response.output_text.delta":
            delta = event.get("delta") or ""
            content += delta
            await emit_progress(on_progress, delta)
        elif event_type == "response.function_call_arguments.delta":
            append_responses_tool_call_arguments(
                tool_call_buffers, event.get("call_id"), event.get("delta")
            )
        elif event_type == "response.function_call_arguments.done":
            replace_responses_tool_call_arguments(
                tool_call_buffers, event.get("call_id"), event.get("arguments")
            )
        elif event_type == "response.output_item.done":
            item = event.get("item") or {}
            tool_call = build_responses_tool_call_request(item, tool_call_buffers)
            if tool_call is not None:
                tool_calls.append(tool_call)
        elif event_type == "response.completed":
            status = (event.get("response") or {}).get("status")
            finish_reason = _map_finish_reason(status)
        elif event_type in {"error", "response.failed"}:
            raise RuntimeError("Codex response failed")

    return content, tool_calls, finish_reason


_FINISH_REASON_MAP = {
    "completed": "stop",
    "incomplete": "length",
    "failed": "error",
    "cancelled": "error",
}


def _map_finish_reason(status: str | None) -> str:
    return _FINISH_REASON_MAP.get(status or "completed", "stop")


def _friendly_error(status_code: int, raw: str) -> str:
    if status_code == 429:
        return "ChatGPT usage quota exceeded or rate limit triggered. Please try again later."
    return f"HTTP {status_code}: {raw}"
