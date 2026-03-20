from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from bao.providers.base import (
    ChatRequest,
    LLMResponse,
    ToolCallRequest,
    build_tool_call_request,
    normalize_tool_calls,
)
from bao.providers.retry import (
    DEFAULT_BASE_DELAY,
    DEFAULT_MAX_RETRIES,
    emit_progress,
    emit_progress_reset,
    safe_error_text,
)
from bao.providers.runtime import (
    ProviderExecutionRequest,
    ProviderRetryPolicy,
    ProviderRuntimeExecutor,
)

from ._openai_provider_common import sanitize_messages

_MAX_RETRIES = DEFAULT_MAX_RETRIES
_BASE_DELAY = DEFAULT_BASE_DELAY


@dataclass(slots=True)
class _CompletionStreamState:
    content: str = ""
    finish_reason: str = "stop"
    reasoning_content: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls_acc: dict[int, dict[str, Any]] = field(default_factory=dict)


def build_completions_params(request: ChatRequest) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": request.model,
        "messages": sanitize_messages(request.messages),
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
        "stream": True,
    }
    if request.tools:
        params["tools"] = request.tools
        params["tool_choice"] = "auto"
    if request.reasoning_effort:
        params["reasoning_effort"] = request.reasoning_effort
    if request.service_tier:
        params["service_tier"] = request.service_tier
    return params


async def run_completions_chat(provider: Any, request: ChatRequest) -> LLMResponse:
    retry_count = 0
    state = _CompletionStreamState()
    executor = ProviderRuntimeExecutor(
        provider.provider_name,
        partial_content=lambda: state.content or None,
    )

    async def _on_retry(exc: BaseException, attempt: int, delay: float) -> None:
        nonlocal retry_count
        retry_count = attempt + 1
        await emit_progress_reset(request.on_progress)
        logger.warning(
            "⚠️ LLM 重试中 / retrying: transient error (attempt {}/{}), in {:.1f}s: {}",
            attempt + 1,
            _MAX_RETRIES + 1,
            delay,
            safe_error_text(exc),
        )

    result = await executor.run(
        lambda: _stream_completions(provider, request, state),
        ProviderExecutionRequest(
            retry_policy=ProviderRetryPolicy(max_retries=_MAX_RETRIES, base_delay=_BASE_DELAY),
            on_retry=_on_retry,
            error_prefix="Error calling LLM",
            progress_error_prefix="Error calling LLM progress callback",
        ),
    )
    if retry_count > 0 and result.finish_reason == "error":
        logger.error(
            "❌ LLM 最终失败 / final failure: after {} attempts: {}",
            retry_count + 1,
            result.content or "unknown error",
        )
    return result


async def _stream_completions(
    provider: Any,
    request: ChatRequest,
    state: _CompletionStreamState,
) -> LLMResponse:
    state.content = ""
    state.finish_reason = "stop"
    state.reasoning_content = None
    state.usage = {}
    state.tool_calls_acc = {}
    stream = await provider._get_client().chat.completions.create(**build_completions_params(request))
    async for chunk in stream:
        _update_usage_from_chunk(state, chunk)
        if not getattr(chunk, "choices", None):
            continue
        await _consume_chunk(state, chunk, request)
    return LLMResponse(
        content=state.content or None,
        tool_calls=_parse_tool_calls(state.tool_calls_acc),
        finish_reason=state.finish_reason,
        usage=state.usage,
        reasoning_content=state.reasoning_content,
    )


def _update_usage_from_chunk(state: _CompletionStreamState, chunk: Any) -> None:
    usage = getattr(chunk, "usage", None)
    if not usage:
        return
    state.usage = {
        "prompt_tokens": usage.prompt_tokens or 0,
        "completion_tokens": usage.completion_tokens or 0,
        "total_tokens": usage.total_tokens or 0,
    }


async def _consume_chunk(state: _CompletionStreamState, chunk: Any, request: ChatRequest) -> None:
    choice = chunk.choices[0]
    delta = choice.delta
    if delta.content:
        state.content += delta.content
        await emit_progress(request.on_progress, delta.content)
    reasoning = getattr(delta, "reasoning_content", None)
    if reasoning:
        state.reasoning_content = (state.reasoning_content or "") + reasoning
    _collect_tool_call_deltas(state.tool_calls_acc, getattr(delta, "tool_calls", None))
    if choice.finish_reason:
        state.finish_reason = choice.finish_reason


def _collect_tool_call_deltas(accumulator: dict[int, dict[str, Any]], tool_calls: Any) -> None:
    for tool_call in tool_calls or []:
        entry = accumulator.setdefault(
            tool_call.index,
            {"id": tool_call.id or "", "name": tool_call.function.name or "", "args": ""},
        )
        if tool_call.function and tool_call.function.arguments:
            entry["args"] += tool_call.function.arguments
        if tool_call.id:
            entry["id"] = tool_call.id
        if tool_call.function and tool_call.function.name:
            entry["name"] = tool_call.function.name


def _parse_tool_calls(tool_calls_acc: dict[int, dict[str, Any]]) -> list[ToolCallRequest]:
    parsed = []
    for index in sorted(tool_calls_acc):
        item = tool_calls_acc[index]
        parsed.append(
            build_tool_call_request(
                id_=item["id"],
                name=item["name"],
                arguments_value=item["args"],
            )
        )
    return parsed


def parse_completions_response(response: Any) -> LLMResponse:
    choice = response.choices[0]
    message = choice.message
    usage = {}
    raw_usage = getattr(response, "usage", None)
    if raw_usage:
        usage = {
            "prompt_tokens": raw_usage.prompt_tokens,
            "completion_tokens": raw_usage.completion_tokens,
            "total_tokens": raw_usage.total_tokens,
        }
    return LLMResponse(
        content=message.content,
        tool_calls=normalize_tool_calls(message),
        finish_reason=choice.finish_reason or "stop",
        usage=usage,
        reasoning_content=getattr(message, "reasoning_content", None),
    )
