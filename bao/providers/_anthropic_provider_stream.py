from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from bao.providers.base import ChatRequest, LLMResponse, ToolCallRequest, build_tool_call_request
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

from ._anthropic_provider_common import budget_from_reasoning_effort, supports_extended_thinking

_MAX_RETRIES = DEFAULT_MAX_RETRIES
_BASE_DELAY = DEFAULT_BASE_DELAY

@dataclass(slots=True)
class _AnthropicStreamState:
    content: str = ""
    reasoning_content: str | None = None
    thinking_blocks: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    current_tool_id: str | None = None
    current_tool_name: str | None = None
    partial_json: str = ""


def build_request_kwargs(provider: Any, request: ChatRequest) -> dict[str, Any]:
    system_prompt, anthropic_messages = provider._convert_messages(request.messages)
    request_kwargs: dict[str, Any] = {
        "model": request.model,
        "max_tokens": max(1, request.max_tokens),
        "temperature": request.temperature,
        "messages": anthropic_messages,
    }
    if system_prompt:
        request_kwargs["system"] = system_prompt
    if request.tools:
        request_kwargs["tools"] = provider._convert_tools(request.tools)
    thinking = _resolve_thinking(provider, request)
    if thinking:
        request_kwargs["thinking"] = thinking
    return request_kwargs


def _resolve_thinking(provider: Any, request: ChatRequest) -> Any:
    if isinstance(request.reasoning_effort, str) and request.reasoning_effort.strip().lower() == "off":
        return None
    if request.thinking is not None:
        return request.thinking
    effort_budget = budget_from_reasoning_effort(request.reasoning_effort)
    if effort_budget:
        return {"type": "adaptive", "budget_tokens": effort_budget}
    if supports_extended_thinking(request.model):
        return {"type": "adaptive", "budget_tokens": 1024}
    return None


async def run_chat(provider: Any, request: ChatRequest) -> LLMResponse:
    retry_count = 0
    state = _AnthropicStreamState()
    executor = ProviderRuntimeExecutor("anthropic", partial_content=lambda: state.content or None)

    async def _on_retry(exc: BaseException, attempt: int, delay: float) -> None:
        nonlocal retry_count
        retry_count = attempt + 1
        await emit_progress_reset(request.on_progress)
        logger.warning(
            "⚠️ Anthropic 重试中 / retrying: transient error (attempt {}/{}), in {:.1f}s: {}",
            attempt + 1,
            _MAX_RETRIES + 1,
            delay,
            safe_error_text(exc),
        )

    result = await executor.run(
        lambda: _stream_chat(provider, request, state),
        ProviderExecutionRequest(
            retry_policy=ProviderRetryPolicy(max_retries=_MAX_RETRIES, base_delay=_BASE_DELAY),
            on_retry=_on_retry,
            error_prefix="Error calling Anthropic",
            progress_error_prefix="Error calling Anthropic progress callback",
        ),
    )
    if retry_count > 0 and result.finish_reason == "error":
        logger.error(
            "❌ Anthropic 最终失败 / final failure: after {} attempts: {}",
            retry_count + 1,
            result.content or "unknown error",
        )
    return result


async def _stream_chat(provider: Any, request: ChatRequest, state: _AnthropicStreamState) -> LLMResponse:
    state.content = ""
    state.reasoning_content = None
    state.thinking_blocks = []
    state.tool_calls = []
    state.current_tool_id = None
    state.current_tool_name = None
    state.partial_json = ""
    async with provider._get_client().messages.stream(**build_request_kwargs(provider, request)) as stream:
        async for event in stream:
            await _consume_stream_event(state, event, request.on_progress)
        final_message = await stream.get_final_message()
    usage = {
        "prompt_tokens": final_message.usage.input_tokens,
        "completion_tokens": final_message.usage.output_tokens,
        "total_tokens": final_message.usage.input_tokens + final_message.usage.output_tokens,
    }
    for block in getattr(final_message, "content", []) or []:
        if getattr(block, "type", None) == "thinking":
            state.thinking_blocks.append({"type": "thinking", "thinking": str(getattr(block, "thinking", "") or "")})
    return LLMResponse(
        content=state.content or None,
        tool_calls=state.tool_calls,
        finish_reason=_finish_reason(final_message.stop_reason),
        usage=usage,
        reasoning_content=state.reasoning_content,
        thinking_blocks=state.thinking_blocks or None,
    )


async def _consume_stream_event(state: _AnthropicStreamState, event: Any, on_progress: Any) -> None:
    if event.type == "content_block_start" and getattr(event.content_block, "type", None) == "tool_use":
        state.current_tool_id = event.content_block.id
        state.current_tool_name = event.content_block.name
        state.partial_json = ""
        return
    if event.type == "content_block_delta":
        await _consume_delta(state, event.delta, on_progress)
        return
    if event.type == "content_block_stop" and state.current_tool_id and state.current_tool_name:
        state.tool_calls.append(
            build_tool_call_request(
                id_=state.current_tool_id,
                name=state.current_tool_name,
                arguments_value=state.partial_json,
            )
        )
        state.current_tool_id = None
        state.current_tool_name = None
        state.partial_json = ""


async def _consume_delta(state: _AnthropicStreamState, delta: Any, on_progress: Any) -> None:
    if delta.type == "text_delta":
        state.content += delta.text
        await emit_progress(on_progress, delta.text)
        return
    if delta.type == "input_json_delta":
        state.partial_json += delta.partial_json
        return
    if delta.type == "thinking_delta":
        state.reasoning_content = (state.reasoning_content or "") + delta.thinking
def _finish_reason(stop_reason: str | None) -> str:
    if stop_reason == "end_turn":
        return "stop"
    if stop_reason == "max_tokens":
        return "length"
    if stop_reason == "tool_use":
        return "tool_calls"
    return stop_reason or "stop"
