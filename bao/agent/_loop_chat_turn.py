from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from bao.agent import shared
from bao.agent.protocol import StreamEvent, StreamEventType
from bao.agent.tool_exposure import ToolExposureSnapshot
from bao.providers.retry import PROGRESS_RESET


@dataclass(frozen=True, slots=True)
class ChatOnceRequest:
    messages: list[dict[str, Any]]
    initial_messages: list[dict[str, Any]]
    iteration: int
    on_progress: Callable[[str], Awaitable[None]] | None
    current_task_ref: asyncio.Task[None] | None
    tool_signal_text: str | None
    force_final_response: bool
    counters: Any
    on_event: Callable[[StreamEvent], Awaitable[None]] | None = None


async def chat_once_with_selected_tools(
    loop: Any,
    request: ChatOnceRequest,
) -> tuple[Any, ToolExposureSnapshot]:
    await _emit_reset_if_needed(request)
    stream_progress = _build_stream_progress(
        loop,
        on_progress=request.on_progress,
        on_event=request.on_event,
        current_task_ref=request.current_task_ref,
    )
    tool_exposure = loop._build_tool_exposure_snapshot(
        initial_messages=request.initial_messages,
        tool_signal_text=request.tool_signal_text,
        force_final_response=request.force_final_response,
    )
    current_tools = list(tool_exposure.tool_definitions)
    messages = loop._apply_available_tools_to_messages(
        request.messages,
        list(tool_exposure.ordered_tool_names),
    )
    loop._sample_tool_schema_if_needed(
        current_tools=current_tools,
        iteration=request.iteration,
        counters=request.counters,
    )
    response = await shared.call_provider_chat(
        shared.ProviderChatRequest(
            provider=loop.provider,
            request=shared.ChatRequest(
                messages=messages,
                tools=current_tools,
                model=loop.model,
                temperature=loop.temperature,
                max_tokens=loop.max_tokens,
                reasoning_effort=loop.reasoning_effort,
                service_tier=loop.service_tier,
                on_progress=stream_progress,
                source="main",
            ),
            patched_log_label="Patched",
        )
    )
    return response, tool_exposure


async def _emit_reset_if_needed(request: ChatOnceRequest) -> None:
    if request.iteration <= 1:
        return
    if request.on_progress:
        await request.on_progress(PROGRESS_RESET)
    if request.on_event:
        await request.on_event(StreamEvent(type=StreamEventType.RESET))


def _build_stream_progress(
    loop: Any,
    *,
    on_progress: Callable[[str], Awaitable[None]] | None,
    on_event: Callable[[StreamEvent], Awaitable[None]] | None,
    current_task_ref: asyncio.Task[None] | None,
) -> Callable[[str], Awaitable[None]] | None:
    if on_progress is None and on_event is None:
        return None

    async def _emit_progress(chunk: str) -> None:
        if on_progress:
            await on_progress(chunk)
        if on_event:
            await on_event(StreamEvent(type=StreamEventType.DELTA, text=chunk))

    if current_task_ref is None:
        return _emit_progress

    async def _interruptable_progress(chunk: str) -> None:
        if loop._session_runs.is_interrupted(current_task_ref):
            from bao.providers.retry import StreamInterruptedError

            raise StreamInterruptedError("soft interrupt during streaming")
        await _emit_progress(chunk)

    return _interruptable_progress
