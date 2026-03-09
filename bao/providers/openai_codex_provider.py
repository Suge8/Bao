"""OpenAI Codex Responses Provider."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, AsyncGenerator, Awaitable, Callable

import httpx
from oauth_cli_kit import get_token as get_codex_token

from bao.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from bao.providers.responses_compat import (
    append_responses_tool_call_arguments,
    build_responses_tool_call_request,
    convert_messages_to_responses,
    convert_tools_to_responses,
    replace_responses_tool_call_arguments,
    start_responses_tool_call,
)
from bao.providers.retry import (
    ProgressCallbackError,
    StreamInterruptedError,
    emit_progress,
    safe_error_text,
)

DEFAULT_CODEX_URL = "https://chatgpt.com/backend-api/codex/responses"
DEFAULT_ORIGINATOR = "Bao"


class OpenAICodexProvider(LLMProvider):
    """Use Codex OAuth to call the Responses API."""

    def __init__(self, default_model: str = "openai-codex/gpt-5.1-codex"):
        super().__init__(api_key=None, api_base=None)
        self.default_model = default_model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        del max_tokens, temperature
        model = model or self.default_model
        reasoning_effort = kwargs.get("reasoning_effort")
        if not isinstance(reasoning_effort, str):
            reasoning_effort = None
        else:
            effort = reasoning_effort.strip().lower()
            reasoning_effort = effort if effort in {"low", "medium", "high"} else None
        system_prompt, input_items = convert_messages_to_responses(messages)

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
            "prompt_cache_key": _prompt_cache_key(messages),
        }
        if reasoning_effort:
            body["reasoning"] = {"effort": reasoning_effort}

        if tools:
            body["tools"] = convert_tools_to_responses(tools)
            body["tool_choice"] = "auto"
            body["parallel_tool_calls"] = True

        url = DEFAULT_CODEX_URL

        try:
            content, tool_calls, finish_reason = await _request_codex(
                url, headers, body, verify=True, on_progress=on_progress
            )
            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )
        except asyncio.CancelledError:
            raise
        except ProgressCallbackError as exc:
            if isinstance(exc, StreamInterruptedError):
                return LLMResponse(content=None, finish_reason="interrupted")
            cause = exc.__cause__ or exc
            return LLMResponse(
                content=f"Error calling Codex progress callback: {safe_error_text(cause)}",
                finish_reason="error",
            )
        except Exception as e:
            return LLMResponse(
                content=f"Error calling Codex: {safe_error_text(e)}",
                finish_reason="error",
            )

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


async def _request_codex(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    verify: bool,
    on_progress: Callable[[str], Awaitable[None]] | None = None,
) -> tuple[str, list[ToolCallRequest], str]:
    async with httpx.AsyncClient(timeout=60.0, verify=verify) as client:
        async with client.stream("POST", url, headers=headers, json=body) as response:
            if response.status_code != 200:
                text = await response.aread()
                raise RuntimeError(
                    _friendly_error(response.status_code, text.decode("utf-8", "ignore"))
                )
            return await _consume_sse(response, on_progress=on_progress)


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
