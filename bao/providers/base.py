"""Base LLM provider interface."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import json_repair


@dataclass
class ToolCallRequest:
    """A tool call request from the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str | None = None
    argument_parse_error: str | None = None
    provider_specific_fields: dict[str, Any] | None = None
    function_provider_specific_fields: dict[str, Any] | None = None

    def to_openai_tool_call(self) -> dict[str, Any]:
        serialized_arguments = json.dumps(self.arguments, ensure_ascii=False)
        if self.argument_parse_error and isinstance(self.raw_arguments, str):
            serialized_arguments = self.raw_arguments
        tool_call = {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": serialized_arguments,
            },
        }
        if self.provider_specific_fields:
            tool_call["provider_specific_fields"] = self.provider_specific_fields
        if self.function_provider_specific_fields:
            tool_call["function"]["provider_specific_fields"] = self.function_provider_specific_fields
        return tool_call


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_content: str | None = None  # Kimi, DeepSeek-R1 etc.
    thinking_blocks: list[dict[str, Any]] | None = None

    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return len(self.tool_calls) > 0


@dataclass(frozen=True)
class ProviderCapabilitySnapshot:
    provider_name: str
    default_api_mode: str = "native"
    supported_api_modes: tuple[str, ...] = ("native",)
    supports_streaming: bool = True
    supports_tools: bool = True
    supports_reasoning_effort: bool = False
    supports_service_tier: bool = False
    supports_prompt_caching: bool = False
    supports_thinking: bool = False


@dataclass(frozen=True, slots=True)
class ChatRequest:
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] | None = None
    model: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.1
    on_progress: Callable[[str], Awaitable[None]] | None = None
    reasoning_effort: str | None = None
    service_tier: str | None = None
    source: str = "main"
    thinking: Any = None
    thinking_budget: int | None = None


def _serialize_raw_arguments(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _parse_tool_arguments(value: Any) -> tuple[dict[str, Any], str | None, str | None]:
    if isinstance(value, dict):
        return value, None, None
    raw_arguments = _serialize_raw_arguments(value)
    if isinstance(value, str):
        try:
            parsed = json_repair.loads(value)
        except Exception:
            return {}, raw_arguments, "tool arguments must decode to a JSON object"
        if isinstance(parsed, dict):
            return parsed, raw_arguments, None
        return {}, raw_arguments, "tool arguments must decode to a JSON object"
    if value is None:
        return {}, None, None
    return {}, raw_arguments, "tool arguments must be a JSON object"


def build_tool_call_request(id_: str, name: str, arguments_value: Any) -> ToolCallRequest:
    args, raw_arguments, parse_error = _parse_tool_arguments(arguments_value)
    return ToolCallRequest(
        id=id_,
        name=name,
        arguments=args,
        raw_arguments=raw_arguments,
        argument_parse_error=parse_error,
    )


def _normalize_openai_tool_calls(message: Any) -> list[ToolCallRequest]:
    return [
        build_tool_call_request(tc.id, tc.function.name, tc.function.arguments)
        for tc in message.tool_calls
    ]


def _normalize_legacy_function_call(message: Any) -> list[ToolCallRequest]:
    fc = message.function_call
    return [build_tool_call_request("fc_0", fc.name, fc.arguments)]


def _normalize_content_blocks(content: Any) -> list[ToolCallRequest]:
    tool_calls: list[ToolCallRequest] = []
    if content and isinstance(content, list):
        for i, block in enumerate(content):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tool_calls.append(
                    build_tool_call_request(
                        block.get("id", f"tu_{i}"),
                        block.get("name", "unknown"),
                        block.get("input", {}),
                    )
                )
    return tool_calls


def normalize_tool_calls(message: Any) -> list[ToolCallRequest]:
    """Extract tool calls from any LLM response format (OpenAI/Legacy/Anthropic)."""
    if hasattr(message, "tool_calls") and message.tool_calls:
        return _normalize_openai_tool_calls(message)
    if hasattr(message, "function_call") and message.function_call:
        return _normalize_legacy_function_call(message)
    return _normalize_content_blocks(getattr(message, "content", None))


_build_tool_call_request = build_tool_call_request


class LLMProvider(ABC):
    def __init__(self, api_key: str | None = None, api_base: str | None = None):
        self.api_key = api_key
        self.api_base = api_base

    @abstractmethod
    async def chat(self, request: ChatRequest) -> LLMResponse:
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        pass

    def get_capability_snapshot(self, model: str | None = None) -> ProviderCapabilitySnapshot:
        del model
        return ProviderCapabilitySnapshot(
            provider_name=self.__class__.__name__,
        )
