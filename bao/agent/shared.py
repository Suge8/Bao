"""Shared utilities for AgentLoop and SubagentManager."""

from __future__ import annotations

from bao.providers.base import ChatRequest

from ._shared_common import (
    SUBAGENT_RESULT_EVENT_TYPE,
    ProviderChatRequest,
    ScreenshotMarkerRequest,
    SubagentResultEvent,
    SubagentResultEventRequest,
    SubagentResultStatus,
    build_subagent_result_event,
    call_provider_chat,
    handle_screenshot_marker,
    maybe_backoff_empty_final,
    parse_llm_json,
    parse_subagent_result_payload,
    strip_think_tags,
)
from ._shared_context import CompactMessagesRequest, compact_messages, patch_dangling_tool_results
from ._shared_experience import (
    CompressStatePromptRequest,
    CompressStateRequest,
    ExperienceLLMFn,
    ExperienceLLMRequest,
    SufficiencyRequest,
    _validate_state,
    call_experience_llm,
    check_sufficiency,
    compress_state,
)
from ._shared_tool_errors import has_tool_error, parse_tool_error
from ._shared_trace import (
    ToolTraceEntryRequest,
    build_tool_trace_entry,
    push_failed_direction,
    sanitize_trace_text,
    sanitize_visible_text,
    summarize_tool_args_for_trace,
)

__all__ = [
    "ExperienceLLMFn",
    "ExperienceLLMRequest",
    "CompressStateRequest",
    "CompressStatePromptRequest",
    "SufficiencyRequest",
    "CompactMessagesRequest",
    "ChatRequest",
    "ProviderChatRequest",
    "ScreenshotMarkerRequest",
    "SUBAGENT_RESULT_EVENT_TYPE",
    "SubagentResultEvent",
    "SubagentResultEventRequest",
    "SubagentResultStatus",
    "ToolTraceEntryRequest",
    "_validate_state",
    "build_subagent_result_event",
    "build_tool_trace_entry",
    "call_experience_llm",
    "call_provider_chat",
    "check_sufficiency",
    "compact_messages",
    "compress_state",
    "handle_screenshot_marker",
    "has_tool_error",
    "maybe_backoff_empty_final",
    "parse_llm_json",
    "parse_subagent_result_payload",
    "parse_tool_error",
    "patch_dangling_tool_results",
    "push_failed_direction",
    "sanitize_trace_text",
    "sanitize_visible_text",
    "strip_think_tags",
    "summarize_tool_args_for_trace",
]
