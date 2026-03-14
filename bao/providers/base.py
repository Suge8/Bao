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


def normalize_tool_calls(message: Any) -> list[ToolCallRequest]:
    """Extract tool calls from any LLM response format (OpenAI/Legacy/Anthropic)."""
    tool_calls: list[ToolCallRequest] = []

    def _append_tool_call(
        *,
        id_: str,
        name: str,
        arguments_value: Any,
    ) -> None:
        args, raw_arguments, parse_error = parse_args(arguments_value)
        tool_calls.append(
            ToolCallRequest(
                id=id_,
                name=name,
                arguments=args,
                raw_arguments=raw_arguments,
                argument_parse_error=parse_error,
            )
        )

    def _serialize_raw_arguments(value: Any) -> str | None:
        if isinstance(value, str):
            return value
        if value is None:
            return None
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)

    def parse_args(value: Any) -> tuple[dict[str, Any], str | None, str | None]:
        if isinstance(value, dict):
            return value, None, None
        raw_arguments = _serialize_raw_arguments(value)
        if isinstance(value, str):
            try:
                parsed = json_repair.loads(value)
            except Exception as exc:
                return {}, raw_arguments, str(exc)
            if isinstance(parsed, dict):
                return parsed, raw_arguments, None
            return {}, raw_arguments, "tool arguments must decode to a JSON object"
        if value is None:
            return {}, None, None
        return {}, raw_arguments, "tool arguments must be a JSON object"

    if hasattr(message, "tool_calls") and message.tool_calls:
        for tc in message.tool_calls:
            _append_tool_call(id_=tc.id, name=tc.function.name, arguments_value=tc.function.arguments)
        return tool_calls

    if hasattr(message, "function_call") and message.function_call:
        fc = message.function_call
        _append_tool_call(id_="fc_0", name=fc.name, arguments_value=fc.arguments)
        return tool_calls

    content = getattr(message, "content", None)
    if content and isinstance(content, list):
        for i, block in enumerate(content):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                _append_tool_call(
                    id_=block.get("id", f"tu_{i}"),
                    name=block.get("name", "unknown"),
                    arguments_value=block.get("input", {}),
                )

    return tool_calls


class LLMProvider(ABC):
    def __init__(self, api_key: str | None = None, api_base: str | None = None):
        self.api_key = api_key
        self.api_base = api_base

    @abstractmethod
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
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        pass
