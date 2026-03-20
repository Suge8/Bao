from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from google.genai import types

from bao.providers.base import ChatRequest, LLMResponse, ToolCallRequest, build_tool_call_request
from bao.providers.retry import emit_progress
from bao.providers.runtime import ProviderExecutionRequest, ProviderRuntimeExecutor

from ._gemini_provider_common import (
    convert_messages,
    convert_tools,
    split_system_instruction,
    thinking_budget_from_effort,
)


@dataclass(slots=True)
class _GeminiStreamState:
    content: str = ""
    reasoning_content: str | None = None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)


async def run_chat(provider: Any, request: ChatRequest) -> LLMResponse:
    state = _GeminiStreamState()
    executor = ProviderRuntimeExecutor("gemini", partial_content=lambda: state.content or None)

    async def _run_once() -> LLMResponse:
        result = await _stream_generate_content(provider, request)
        state.content = result.content or ""
        return result

    return await executor.run(
        _run_once,
        ProviderExecutionRequest(
            error_prefix="Error calling Gemini",
            progress_error_prefix="Error calling Gemini progress callback",
        ),
    )


async def _stream_generate_content(provider: Any, request: ChatRequest) -> LLMResponse:
    system_prompt, filtered_messages = split_system_instruction(request.messages)
    contents = convert_messages(filtered_messages)
    config = _build_config(request, system_prompt)
    state = _GeminiStreamState()
    chunk = None
    async for chunk in await provider._client.aio.models.generate_content_stream(
        model=request.model,
        contents=cast(Any, contents),
        config=config,
    ):
        await _consume_chunk(state, chunk, request.on_progress)
    return LLMResponse(
        content=state.content or None,
        tool_calls=state.tool_calls,
        finish_reason=_finish_reason(chunk),
        usage=_usage(chunk),
        reasoning_content=state.reasoning_content,
    )


def _build_config(request: ChatRequest, system_prompt: Any) -> types.GenerateContentConfig:
    config = types.GenerateContentConfig(
        max_output_tokens=request.max_tokens,
        temperature=request.temperature,
        system_instruction=system_prompt,
    )
    if request.tools:
        config.tools = cast(Any, convert_tools(request.tools))
    thinking = request.thinking
    effort_budget = thinking_budget_from_effort(request.reasoning_effort)
    if effort_budget is not None and not thinking:
        thinking = True
    if thinking:
        config.thinking_config = types.ThinkingConfig(
            include_thoughts=True,
            thinking_budget=request.thinking_budget or effort_budget or 2048,
        )
    return config


async def _consume_chunk(
    state: _GeminiStreamState,
    chunk: Any,
    on_progress: Any,
) -> None:
    if not chunk.candidates:
        return
    candidate = chunk.candidates[0]
    if not candidate.content or not candidate.content.parts:
        return
    for part in candidate.content.parts:
        if part.text:
            state.content += part.text
            await emit_progress(on_progress, part.text)
        if getattr(part, "thought", None):
            state.reasoning_content = (state.reasoning_content or "") + str(part.thought)
        if part.function_call:
            state.tool_calls.append(_tool_call(part.function_call))


def _tool_call(function_call: Any) -> ToolCallRequest:
    arguments_value = (
        function_call.args if isinstance(function_call.args, dict) else function_call.args
    )
    return build_tool_call_request(
        id_=getattr(function_call, "id", None) or f"call_{function_call.name}",
        name=function_call.name or "unknown",
        arguments_value=arguments_value,
    )


def _finish_reason(chunk: Any) -> str:
    if not chunk or not chunk.candidates:
        return "stop"
    return {
        "STOP": "stop",
        "MAX_TOKENS": "length",
        "SAFETY": "content_filter",
        "RECITATION": "content_filter",
    }.get(str(chunk.candidates[0].finish_reason), "stop")


def _usage(chunk: Any) -> dict[str, int]:
    usage = getattr(chunk, "usage_metadata", None)
    if not usage:
        return {}
    return {
        "prompt_tokens": getattr(usage, "prompt_token_count", 0),
        "completion_tokens": getattr(usage, "candidates_token_count", 0),
        "total_tokens": getattr(usage, "total_token_count", 0),
    }
