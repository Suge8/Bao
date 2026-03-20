"""Anthropic Provider — native SDK with Extended Thinking and Prompt Caching support."""

from __future__ import annotations

from typing import Any

from bao.providers.base import ChatRequest, LLMProvider, LLMResponse, ProviderCapabilitySnapshot

from ._anthropic_provider_common import (
    _PROXY_SAFE_DEFAULT_HEADERS,
    apply_cache_control,
    budget_from_reasoning_effort,
    convert_content_blocks,
    convert_messages,
    convert_tools,
    convert_user_content,
    parse_response,
    supports_extended_thinking,
)
from ._anthropic_provider_stream import run_chat


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "claude-sonnet-4-20250514",
        base_url: str | None = None,
    ):
        super().__init__(api_key, None)
        self.default_model = default_model
        self._client_kwargs: dict[str, Any] = {"api_key": api_key, "max_retries": 0}
        if base_url:
            self._client_kwargs["base_url"] = base_url.rstrip("/")
            self._client_kwargs["default_headers"] = _PROXY_SAFE_DEFAULT_HEADERS
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic(**self._client_kwargs)
        return self._client

    def _resolve_model(self, model: str) -> str:
        return model.split("/", 1)[1] if "/" in model else model

    def _supports_extended_thinking(self, model: str) -> bool:
        return supports_extended_thinking(model)

    def get_capability_snapshot(self, model: str | None = None) -> ProviderCapabilitySnapshot:
        resolved_model = self._resolve_model(model or self.default_model)
        return ProviderCapabilitySnapshot(
            provider_name="anthropic",
            default_api_mode="messages",
            supported_api_modes=("messages",),
            supports_streaming=True,
            supports_tools=True,
            supports_reasoning_effort=True,
            supports_service_tier=False,
            supports_prompt_caching=True,
            supports_thinking=self._supports_extended_thinking(resolved_model),
        )

    @staticmethod
    def _budget_from_reasoning_effort(reasoning_effort: str | None) -> int | None:
        return budget_from_reasoning_effort(reasoning_effort)

    def _convert_messages(self, messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
        return convert_messages(messages)

    def _convert_user_content(self, content: Any) -> str | list[dict[str, Any]]:
        return convert_user_content(content)

    def _convert_content_blocks(self, content: Any) -> str:
        return convert_content_blocks(content)

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return convert_tools(tools)

    def _apply_cache_control(
        self,
        system_prompt: str | None,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> tuple[str | list[dict[str, Any]] | None, list[dict[str, Any]], list[dict[str, Any]] | None]:
        return apply_cache_control(system_prompt, messages, tools)

    async def chat(self, request: ChatRequest) -> LLMResponse:
        return await run_chat(
            self,
            ChatRequest(
                messages=request.messages,
                tools=request.tools,
                model=self._resolve_model(request.model or self.default_model),
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                on_progress=request.on_progress,
                reasoning_effort=request.reasoning_effort,
                service_tier=request.service_tier,
                source=request.source,
                thinking=request.thinking,
            ),
        )

    def _parse_response(self, response: Any) -> LLMResponse:
        content, tool_calls, reasoning, thinking_blocks, finish_reason, usage = parse_response(response)
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            reasoning_content=reasoning,
            thinking_blocks=thinking_blocks or None,
        )

    def get_default_model(self) -> str:
        return self.default_model
