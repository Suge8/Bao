"""OpenAI-Compatible Provider — supports Responses with automatic fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from bao.providers.api_mode_cache import get_cached_mode
from bao.providers.base import ChatRequest, LLMProvider, LLMResponse, ProviderCapabilitySnapshot

from ._openai_provider_common import (
    _normalize_openai_reasoning_effort,
    _normalize_service_tier,
    apply_cache_control,
    sanitize_messages,
)
from ._openai_provider_completions import parse_completions_response, run_completions_chat
from ._openai_provider_responses_chat import (
    build_responses_body,
    build_responses_headers,
    chat_responses,
    chat_with_probe,
)
from ._openai_provider_responses_stream import (
    build_responses_result,
    consume_responses_stream,
    decode_responses_payload,
    iter_sse_events,
    map_responses_finish_reason,
)


@dataclass(frozen=True)
class OpenAIProviderOptions:
    default_model: str = "gpt-4o"
    extra_headers: dict[str, str] = field(default_factory=dict)
    provider_name: str | None = None
    model_prefix: str | None = None


class OpenAICompatibleProvider(LLMProvider):
    """Universal OpenAI-compatible provider with automatic mode detection."""

    PROMPT_CACHING_PROVIDERS = frozenset({"openrouter", "openai"})

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        options: OpenAIProviderOptions | None = None,
    ):
        super().__init__(api_key, api_base)
        provider_options = options or OpenAIProviderOptions()
        self.default_model = provider_options.default_model
        self.extra_headers = dict(provider_options.extra_headers or {})
        self.provider_name = provider_options.provider_name or "openai"
        self._model_prefix = (provider_options.model_prefix or "").strip().lower()
        self._effective_base = api_base or "https://api.openai.com/v1"
        self._default_headers = {"User-Agent": "Bao/1.0", **self.extra_headers}
        self._api_key_str = api_key or "dummy-key"
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self._api_key_str,
                base_url=self._effective_base,
                default_headers=self._default_headers,
            )
        return self._client

    def _resolve_model(self, model: str) -> str:
        if self._model_prefix and model.lower().startswith(f"{self._model_prefix}/"):
            return model.split("/", 1)[1]
        return model

    @staticmethod
    def _supports_reasoning_effort(model: str) -> bool:
        return model.lower().startswith(("gpt-5", "o1", "o3", "o4"))

    def _supports_prompt_caching(self) -> bool:
        return self.provider_name.lower() in self.PROMPT_CACHING_PROVIDERS

    def get_capability_snapshot(self, model: str | None = None) -> ProviderCapabilitySnapshot:
        resolved_model = self._resolve_model(model or self.default_model)
        supports_reasoning = self._supports_reasoning_effort(resolved_model)
        return ProviderCapabilitySnapshot(
            provider_name=self.provider_name,
            default_api_mode=self._resolve_effective_mode(),
            supported_api_modes=("responses", "completions"),
            supports_streaming=True,
            supports_tools=True,
            supports_reasoning_effort=supports_reasoning,
            supports_service_tier=True,
            supports_prompt_caching=self._supports_prompt_caching(),
            supports_thinking=supports_reasoning,
        )

    def _apply_cache_control(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
        return apply_cache_control(self._supports_prompt_caching(), messages, tools)

    @staticmethod
    def _sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sanitize_messages(messages)

    def _resolve_effective_mode(self) -> str:
        return get_cached_mode(self._effective_base) or "auto"

    @staticmethod
    def _build_responses_result(payload: dict[str, Any]) -> LLMResponse:
        return build_responses_result(payload)

    @staticmethod
    def _decode_responses_payload(response: Any) -> dict[str, Any]:
        return decode_responses_payload(response)

    @staticmethod
    async def _iter_sse_events(response: Any):
        async for event in iter_sse_events(response):
            yield event

    @staticmethod
    def _map_responses_finish_reason(status: str | None) -> str:
        return map_responses_finish_reason(status)

    async def _consume_responses_stream(
        self,
        response: Any,
        on_progress: Callable[[str], Awaitable[None]] | None,
    ) -> LLMResponse:
        return await consume_responses_stream(self, response, on_progress)

    async def chat(self, request: ChatRequest) -> LLMResponse:
        request = self._normalize_chat_request(request)
        resolved_model = self._resolve_model(request.model or self.default_model)
        if self._supports_prompt_caching():
            messages, tools = self._apply_cache_control(request.messages, request.tools)
            request = ChatRequest(
                messages=messages,
                tools=tools,
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                on_progress=request.on_progress,
                reasoning_effort=request.reasoning_effort,
                service_tier=request.service_tier,
                source=request.source,
                thinking=request.thinking,
                thinking_budget=request.thinking_budget,
            )
        request = ChatRequest(
            messages=request.messages,
            tools=request.tools,
            model=resolved_model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            on_progress=request.on_progress,
            reasoning_effort=request.reasoning_effort,
            service_tier=request.service_tier,
            source=request.source,
            thinking=request.thinking,
            thinking_budget=request.thinking_budget,
        )
        mode = self._resolve_effective_mode()
        if mode == "responses":
            return await self._chat_responses(request)
        if mode == "completions":
            return await self._chat_completions(request)
        return await self._chat_with_probe(request)

    def _normalize_chat_request(self, request: ChatRequest) -> ChatRequest:
        model = request.model or self.default_model
        reasoning_effort = _normalize_openai_reasoning_effort(
            request.reasoning_effort,
            allow_off=True,
        )
        if reasoning_effort and not self._supports_reasoning_effort(model):
            reasoning_effort = None
        return ChatRequest(
            messages=request.messages,
            tools=request.tools,
            model=model,
            max_tokens=max(1, request.max_tokens),
            temperature=request.temperature,
            on_progress=request.on_progress,
            reasoning_effort=reasoning_effort,
            service_tier=_normalize_service_tier(request.service_tier),
            source=request.source,
            thinking=request.thinking,
            thinking_budget=request.thinking_budget,
        )

    async def _chat_completions(self, request: ChatRequest) -> LLMResponse:
        return await run_completions_chat(self, request)

    def _build_responses_body(self, request: ChatRequest) -> dict[str, Any]:
        return build_responses_body(request)

    def _build_responses_headers(self) -> dict[str, str]:
        return build_responses_headers(self._api_key_str, self._default_headers)

    async def _chat_responses(self, request: ChatRequest) -> LLMResponse:
        return await chat_responses(self, request)

    async def _chat_with_probe(self, request: ChatRequest) -> LLMResponse:
        return await chat_with_probe(self, request)

    def _parse_completions_response(self, response: Any) -> LLMResponse:
        return parse_completions_response(response)

    def get_default_model(self) -> str:
        return self.default_model
