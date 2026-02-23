"""OpenAI-Compatible Provider — supports OpenAI, OpenRouter, DeepSeek, Groq, and any OpenAI-compatible endpoint."""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from bao.providers.base import LLMProvider, LLMResponse, ToolCallRequest, normalize_tool_calls


# Standard OpenAI chat-completion message keys; extras (e.g. reasoning_content) are stripped for strict providers.
_ALLOWED_MSG_KEYS = frozenset({"role", "content", "tool_calls", "tool_call_id", "name"})


class OpenAICompatibleProvider(LLMProvider):
    """
    Universal OpenAI-compatible provider.

    Supports:
    - OpenAI (api.openai.com)
    - OpenRouter (openrouter.ai)
    - DeepSeek (api.deepseek.com)
    - Groq (api.groq.com)
    - SiliconFlow (api.siliconflow.cn)
    - VolcEngine (ark.cn-beijing.volces.com)
    - vLLM / Ollama / any OpenAI-compatible server

    Set api_base to the provider's endpoint URL. If not set, defaults to OpenAI.
    """

    # Known providers that support prompt caching
    PROMPT_CACHING_PROVIDERS = frozenset({"openrouter", "openai"})

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "gpt-4o",
        extra_headers: dict[str, str] | None = None,
        provider_name: str | None = None,
    ):
        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.extra_headers = extra_headers or {}
        self.provider_name = provider_name or "openai"

        # Build headers
        headers = {"User-Agent": "bao/1.0"}
        if self.extra_headers:
            headers.update(self.extra_headers)

        self._client = AsyncOpenAI(
            api_key=api_key or "dummy-key",
            base_url=api_base or "https://api.openai.com/v1",
            default_headers=headers,
        )

    def _resolve_model(self, model: str) -> str:
        """Strip provider prefix from model name.

        OpenAI-compatible endpoints expect bare model names (e.g., "gpt-4o"),
        not prefixed ones (e.g., "openrouter/gpt-4o" or "deepseek/deepseek-chat").
        """
        # Strip known prefixes
        prefixes_to_strip = (
            "openrouter/",
            "deepseek/",
            "groq/",
            "anthropic/",
            "gemini/",
            "moonshot/",
            "minimax/",
            "qwen/",
            "glm/",
            "zhipu/",
            "vllm/",
            "ollama/",
            "lm-studio/",
        )

        model_lower = model.lower()
        for prefix in prefixes_to_strip:
            if model_lower.startswith(prefix):
                return model[len(prefix) :]

        return model

    def _supports_prompt_caching(self) -> bool:
        """Check if current provider supports prompt caching."""
        return self.provider_name.lower() in self.PROMPT_CACHING_PROVIDERS

    def _apply_cache_control(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
        """Apply cache_control for providers that support it (OpenRouter, OpenAI)."""
        if not self._supports_prompt_caching():
            return messages, tools

        new_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                content = msg["content"]
                if isinstance(content, str):
                    new_content = [
                        {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                    ]
                else:
                    new_content = list(content)
                    new_content[-1] = {**new_content[-1], "cache_control": {"type": "ephemeral"}}
                new_messages.append({**msg, "content": new_content})
            else:
                new_messages.append(msg)

        new_tools = tools
        if tools:
            new_tools = list(tools)
            new_tools[-1] = {**new_tools[-1], "cache_control": {"type": "ephemeral"}}

        return new_messages, new_tools

    @staticmethod
    def _sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Strip non-standard keys and ensure assistant messages have a content key."""
        sanitized = []
        for msg in messages:
            clean = {k: v for k, v in msg.items() if k in _ALLOWED_MSG_KEYS}
            # Strict providers require "content" even when assistant only has tool_calls
            if clean.get("role") == "assistant" and "content" not in clean:
                clean["content"] = None
            sanitized.append(clean)
        return sanitized

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
        Send a chat completion request via OpenAI-compatible API.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional list of tool definitions in OpenAI format.
            model: Model identifier (e.g., 'gpt-4o', 'anthropic/claude-sonnet-4-5').
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with content and/or tool calls.
        """
        original_model = model or self.default_model
        resolved_model = self._resolve_model(original_model)

        # Apply prompt caching if supported
        if self._supports_prompt_caching():
            messages, tools = self._apply_cache_control(messages, tools)

        # Clamp max_tokens
        max_tokens = max(1, max_tokens)

        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": self._sanitize_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = await self._client.chat.completions.create(**kwargs)
            return self._parse_response(response)
        except Exception as e:
            return LLMResponse(
                content=f"Error calling LLM: {str(e)}",
                finish_reason="error",
            )

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse OpenAI-compatible response into LLMResponse."""
        choice = response.choices[0]
        message = choice.message

        tool_calls = normalize_tool_calls(message)

        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        reasoning_content = getattr(message, "reasoning_content", None)

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            reasoning_content=reasoning_content,
        )

    def get_default_model(self) -> str:
        return self.default_model
