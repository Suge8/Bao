"""Anthropic Provider — native SDK with Extended Thinking and Prompt Caching support."""

from __future__ import annotations

from typing import Any

import anthropic

from bao.providers.base import LLMProvider, LLMResponse, ToolCallRequest, normalize_tool_calls


class AnthropicProvider(LLMProvider):
    """
    Anthropic Claude provider using the official SDK.

    Supports:
    - Claude 3.5 Sonnet, 3.7 Sonnet, 3.7 Haiku
    - Extended Thinking (Claude 3.7 Sonnet with thinking enabled)
    - Prompt Caching (cache_control on system messages and tools)
    - Native tool use (tool_use content blocks)

    Models: claude-3-5-sonnet-20241022, claude-3-7-sonnet-20250514, claude-3-7-haiku-20250514, etc.
    """

    # Models that support extended thinking
    EXTENDED_THINKING_MODELS = frozenset(
        {
            "claude-3-7-sonnet-20250514",
            "claude-sonnet-4-20250514",
        }
    )

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "claude-sonnet-4-20250514",
    ):
        super().__init__(api_key, None)
        self.default_model = default_model

        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            max_retries=0,  # Handle retries at the agent level
        )

    def _resolve_model(self, model: str) -> str:
        """Strip 'anthropic/' prefix if present."""
        if model.lower().startswith("anthropic/"):
            return model[len("anthropic/") :]
        return model

    def _supports_extended_thinking(self, model: str) -> bool:
        """Check if model supports extended thinking."""
        model_lower = model.lower()
        return any(think_model in model_lower for think_model in self.EXTENDED_THINKING_MODELS)

    def _convert_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert OpenAI-style messages to Anthropic format.

        Returns: (system_prompt, anthropic_messages)
        """
        system_prompt: str | None = None
        anthropic_messages: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            if role == "system":
                # Anthropic uses system as a separate parameter
                if isinstance(content, str):
                    system_prompt = content
                else:
                    # Convert content blocks
                    system_prompt = self._convert_content_blocks(content)
            elif role == "user":
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": self._convert_user_content(content),
                    }
                )
            elif role == "assistant":
                # Assistant message may have content and/or tool calls
                parts = []
                if content:
                    parts.append({"type": "text", "text": content})

                # Handle tool calls
                for tc in msg.get("tool_calls", []) or []:
                    fn = tc.get("function") or {}
                    parts.append(
                        {
                            "type": "tool_use",
                            "id": tc.get("id", f"tool_{tc.get('name', 'unknown')}"),
                            "name": fn.get("name", ""),
                            "input": fn.get("arguments", {}),
                        }
                    )

                if parts:
                    anthropic_messages.append({"role": "assistant", "content": parts})
            elif role == "tool":
                # Tool result
                tool_content = content if isinstance(content, str) else str(content)
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.get("tool_call_id", "unknown"),
                                "content": tool_content,
                            }
                        ],
                    }
                )

        return system_prompt, anthropic_messages

    def _convert_user_content(self, content: Any) -> str | list[dict[str, Any]]:
        """Convert user message content to Anthropic format."""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == "text":
                    parts.append({"type": "text", "text": item.get("text", "")})
                elif item_type == "image_url":
                    # Handle image URLs
                    url_data = item.get("image_url") or {}
                    url = url_data.get("url", "")
                    # Anthropic expects base64 or media type
                    if url.startswith("data:"):
                        parts.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": url.split(",", 1)[1],
                                },
                            }
                        )
                    else:
                        # For URLs, we'd need to fetch - for now, skip
                        pass
            return parts if parts else ""

        return str(content)

    def _convert_content_blocks(self, content: Any) -> str:
        """Convert content blocks to string for system prompt."""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        texts.append(block.get("text", ""))
            return "\n".join(texts)

        return str(content)

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI function-calling tools to Anthropic tool format."""
        anthropic_tools = []

        for tool in tools:
            fn = (tool.get("function") or {}) if tool.get("type") == "function" else tool
            name = fn.get("name")
            if not name:
                continue

            description = fn.get("description", "")
            parameters = fn.get("parameters") or {}

            anthropic_tools.append(
                {
                    "name": name,
                    "description": description,
                    "input_schema": parameters if isinstance(parameters, dict) else {},
                }
            )

        return anthropic_tools

    def _apply_cache_control(
        self,
        system_prompt: str | None,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]] | None]:
        """Apply cache_control for prompt caching support."""
        new_system = system_prompt
        if system_prompt:
            new_system = [
                {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
            ]

        new_messages = []
        for msg in messages:
            # Add cache_control to last message if it's from user
            if msg.get("role") == "user":
                content = msg.get("content")
                if isinstance(content, str):
                    new_content = [
                        {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                    ]
                elif isinstance(content, list):
                    new_content = list(content)
                    if new_content:
                        new_content[-1] = {
                            **new_content[-1],
                            "cache_control": {"type": "ephemeral"},
                        }
                else:
                    new_content = content
                new_messages.append({**msg, "content": new_content})
            else:
                new_messages.append(msg)

        new_tools = None
        if tools:
            new_tools = list(tools)
            new_tools[-1] = {**new_tools[-1], "cache_control": {"type": "ephemeral"}}

        return new_system, new_messages, new_tools

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Send a chat completion request via Anthropic API.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional list of tool definitions in OpenAI format.
            model: Model identifier (e.g., 'claude-sonnet-4-20250514').
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with content and/or tool calls.
        """
        original_model = model or self.default_model
        resolved_model = self._resolve_model(original_model)

        # Convert messages
        system_prompt, anthropic_messages = self._convert_messages(messages)

        # Prepare request
        request_kwargs: dict[str, Any] = {
            "model": resolved_model,
            "max_tokens": max(1, max_tokens),
            "temperature": temperature,
        }

        # Add system prompt
        if system_prompt:
            request_kwargs["system"] = system_prompt

        # Add messages
        request_kwargs["messages"] = anthropic_messages

        # Add tools
        if tools:
            request_kwargs["tools"] = self._convert_tools(tools)

        # Handle thinking (extended thinking for Claude 3.7)
        thinking = kwargs.get("thinking")
        if thinking is None and self._supports_extended_thinking(resolved_model):
            # Default to enabling thinking for supported models
            thinking = {"type": "enabled", "budget_tokens": 1024}

        if thinking:
            request_kwargs["thinking"] = thinking

        try:
            response = await self._client.messages.create(**request_kwargs)
            return self._parse_response(response)
        except Exception as e:
            return LLMResponse(
                content=f"Error calling Anthropic: {str(e)}",
                finish_reason="error",
            )

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse Anthropic response into LLMResponse."""
        content = ""
        tool_calls: list[ToolCallRequest] = []
        reasoning_content: str | None = None
        finish_reason = "stop"

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCallRequest(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    )
                )
            elif block.type == "thinking":
                reasoning_content = block.thinking

        # Map finish reason
        if response.stop_reason == "end_turn":
            finish_reason = "stop"
        elif response.stop_reason == "max_tokens":
            finish_reason = "length"
        elif response.stop_reason == "tool_use":
            finish_reason = "tool_calls"
        else:
            finish_reason = response.stop_reason or "stop"

        # Usage
        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            reasoning_content=reasoning_content,
        )

    def get_default_model(self) -> str:
        return self.default_model
