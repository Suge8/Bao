"""Google Gemini Provider — native SDK with Thinking Mode support."""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from bao.providers.base import ChatRequest, LLMProvider, LLMResponse, ProviderCapabilitySnapshot

from ._gemini_provider_common import (
    convert_messages,
    convert_tools,
    parse_response,
    thinking_budget_from_effort,
)
from ._gemini_provider_stream import run_chat


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "gemini-2.0-flash",
        base_url: str | None = None,
    ):
        super().__init__(api_key, None)
        self.default_model = default_model
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["http_options"] = types.HttpOptions(base_url=base_url)
        self._client = genai.Client(**client_kwargs)

    def _resolve_model(self, model: str) -> str:
        return model.split("/", 1)[1] if "/" in model else model

    def get_capability_snapshot(self, model: str | None = None) -> ProviderCapabilitySnapshot:
        resolved_model = self._resolve_model(model or self.default_model)
        supports_thinking = resolved_model.startswith("gemini-2.5")
        return ProviderCapabilitySnapshot(
            provider_name="gemini",
            default_api_mode="generate_content",
            supported_api_modes=("generate_content",),
            supports_streaming=True,
            supports_tools=True,
            supports_reasoning_effort=True,
            supports_service_tier=False,
            supports_prompt_caching=False,
            supports_thinking=supports_thinking,
        )

    @staticmethod
    def _thinking_budget_from_effort(reasoning_effort: str | None) -> int | None:
        return thinking_budget_from_effort(reasoning_effort)

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[types.Content]:
        return convert_messages(messages)

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[types.Tool]:
        return convert_tools(tools)

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
                thinking_budget=request.thinking_budget,
            ),
        )

    def _parse_response(self, response: Any) -> LLMResponse:
        return parse_response(response)

    def get_default_model(self) -> str:
        return self.default_model
