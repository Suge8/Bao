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
    provider_specific_fields: dict[str, Any] | None = None
    function_provider_specific_fields: dict[str, Any] | None = None

    def to_openai_tool_call(self) -> dict[str, Any]:
        tool_call = {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments, ensure_ascii=False),
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

    def parse_args(value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            try:
                parsed = json_repair.loads(value)
                value = parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return value if isinstance(value, dict) else {}

    if hasattr(message, "tool_calls") and message.tool_calls:
        for tc in message.tool_calls:
            args = parse_args(tc.function.arguments)
            tool_calls.append(ToolCallRequest(id=tc.id, name=tc.function.name, arguments=args))
        return tool_calls

    if hasattr(message, "function_call") and message.function_call:
        fc = message.function_call
        args = parse_args(fc.arguments)
        tool_calls.append(ToolCallRequest(id="fc_0", name=fc.name, arguments=args))
        return tool_calls

    content = getattr(message, "content", None)
    if content and isinstance(content, list):
        for i, block in enumerate(content):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                input_args = block.get("input", {})
                if not isinstance(input_args, dict):
                    input_args = {}
                tool_calls.append(
                    ToolCallRequest(
                        id=block.get("id", f"tu_{i}"),
                        name=block.get("name", "unknown"),
                        arguments=input_args,
                    )
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
