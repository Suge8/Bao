from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

from bao.providers.api_mode_cache import set_cached_mode
from bao.providers.base import ChatRequest, LLMResponse
from bao.providers.responses_compat import convert_messages_to_responses, convert_tools_to_responses
from bao.providers.retry import DEFAULT_BASE_DELAY, DEFAULT_MAX_RETRIES, emit_progress_reset
from bao.providers.runtime import (
    ProviderError,
    ProviderErrorContext,
    ProviderExecutionRequest,
    ProviderRetryPolicy,
    ProviderRuntimeExecutor,
)

from ._openai_provider_common import (
    _PROBE_FALLBACK_CODES,
    _ResponsesHTTPStatusError,
    _system_prompt_seems_ignored,
)

_MAX_RETRIES = DEFAULT_MAX_RETRIES
_BASE_DELAY = DEFAULT_BASE_DELAY


@dataclass(frozen=True)
class _ResponsesValidationContext:
    on_progress: Any
    system_prompt: str | None


@dataclass(frozen=True)
class _ProbeErrorContext:
    error: ProviderErrorContext
    status_code: int | None = None


def build_responses_body(request: ChatRequest) -> dict[str, Any]:
    system_prompt, input_items = convert_messages_to_responses(request.messages)
    body: dict[str, Any] = {
        "model": request.model,
        "input": input_items,
        "temperature": request.temperature,
        "max_output_tokens": request.max_tokens,
        "store": False,
    }
    if system_prompt:
        body["instructions"] = system_prompt
    if request.tools:
        body["tools"] = convert_tools_to_responses(request.tools)
        body["tool_choice"] = "auto"
    if request.reasoning_effort:
        body["reasoning"] = {"effort": request.reasoning_effort}
    if request.service_tier:
        body["service_tier"] = request.service_tier
    return body


def build_responses_headers(api_key: str, default_headers: dict[str, str]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **default_headers,
    }


async def chat_responses(provider: Any, request: ChatRequest) -> LLMResponse:
    retry_count = 0
    executor = ProviderRuntimeExecutor(provider.provider_name)

    async def _on_retry(exc: BaseException, attempt: int, delay: float) -> None:
        nonlocal retry_count
        retry_count = attempt + 1
        logger.warning(
            "⚠️ 接口重试中 / retrying: [{}] Responses transient error (attempt {}/{}), in {:.1f}s: {}",
            request.source,
            attempt + 1,
            _MAX_RETRIES + 1,
            delay,
            str(exc),
        )

    result = await executor.run(
        lambda: _run_responses_request(provider, request),
        ProviderExecutionRequest(
            retry_policy=ProviderRetryPolicy(max_retries=_MAX_RETRIES, base_delay=_BASE_DELAY),
            on_retry=_on_retry,
            error_prefix="Error calling Responses API",
            progress_error_prefix="Error calling LLM progress callback",
            fallback=lambda exc: _fallback_to_completions(provider, request, exc),
            should_fallback=lambda _exc: True,
        ),
    )
    if retry_count > 0 and result.finish_reason == "error":
        logger.error(
            "❌ Responses 最终失败 / final failure: after {} attempts: {}",
            retry_count + 1,
            result.content or "unknown error",
        )
    return result


async def _run_responses_request(provider: Any, request: ChatRequest) -> LLMResponse:
    await emit_progress_reset(request.on_progress)
    system_prompt, _ = convert_messages_to_responses(request.messages)
    body = build_responses_body(request)
    body["stream"] = True
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", _responses_url(provider), headers=provider._build_responses_headers(), json=body) as response:
            if response.status_code == 200:
                return await _validated_stream_result(
                    provider,
                    response,
                    _ResponsesValidationContext(
                        on_progress=request.on_progress,
                        system_prompt=system_prompt,
                    ),
                )
            if response.status_code in _PROBE_FALLBACK_CODES:
                raise _unsupported_responses_error(provider, response.status_code)
            raise _ResponsesHTTPStatusError(response)


async def _validated_stream_result(
    provider: Any,
    response: Any,
    context: _ResponsesValidationContext,
) -> LLMResponse:
    result = await provider._consume_responses_stream(response, context.on_progress)
    if context.system_prompt and _system_prompt_seems_ignored(context.system_prompt, result.content):
        raise ProviderError(
            provider_name=provider.provider_name,
            code="responses_prompt_ignored",
            message="Responses API ignored the system prompt",
            retryable=False,
            fallback_target="completions",
        )
    return result


def _unsupported_responses_error(provider: Any, status_code: int) -> ProviderError:
    return ProviderError(
        provider_name=provider.provider_name,
        code="responses_unsupported",
        message=f"Responses API unsupported with status {status_code}",
        retryable=False,
        status_code=status_code,
        fallback_target="completions",
    )


async def _fallback_to_completions(provider: Any, request: ChatRequest, exc: ProviderError) -> LLMResponse:
    if exc.code in {"responses_unsupported", "responses_prompt_ignored"}:
        set_cached_mode(provider._effective_base, "completions")
    logger.debug(
        "🤖 回退补全 / fallback: [{}] request failed model={} base={} ({}), trying Chat Completions",
        request.source,
        request.model,
        provider._effective_base,
        exc.message,
    )
    return await provider._chat_completions(request)


async def chat_with_probe(provider: Any, request: ChatRequest) -> LLMResponse:
    executor = ProviderRuntimeExecutor(provider.provider_name)
    return await executor.run(
        lambda: _probe_responses_mode(provider, request),
        ProviderExecutionRequest(
            error_prefix="Error calling Responses API",
            progress_error_prefix="Error calling LLM progress callback",
            fallback=lambda exc: _probe_fallback(provider, request, exc),
            should_fallback=lambda _exc: True,
        ),
    )


async def _probe_responses_mode(provider: Any, request: ChatRequest) -> LLMResponse:
    system_prompt, _ = convert_messages_to_responses(request.messages)
    body = build_responses_body(request)
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(_responses_url(provider), headers=provider._build_responses_headers(), json=body)
    if response.status_code in _PROBE_FALLBACK_CODES:
        raise _probe_error(
            provider,
            f"Responses API not supported ({response.status_code})",
            _ProbeErrorContext(
                error=ProviderErrorContext(
                    code="responses_probe_unsupported",
                    fallback_target="completions",
                ),
                status_code=response.status_code,
            ),
        )
    if response.status_code != 200:
        raise _probe_error(
            provider,
            f"Responses probe returned {response.status_code}",
            _ProbeErrorContext(
                error=ProviderErrorContext(
                    code="responses_probe_failed",
                    fallback_target="completions",
                ),
                status_code=response.status_code,
            ),
        )
    result = provider._build_responses_result(provider._decode_responses_payload(response))
    if system_prompt and _system_prompt_seems_ignored(system_prompt, result.content):
        raise _probe_error(
            provider,
            "Responses probe ignored the system prompt",
            _ProbeErrorContext(
                error=ProviderErrorContext(
                    code="responses_probe_prompt_ignored",
                    fallback_target="completions",
                )
            ),
        )
    set_cached_mode(provider._effective_base, "responses")
    logger.info("🤖 响应已启用 / detected: [{}] Responses API cached", request.source)
    return result


def _probe_error(
    provider: Any,
    message: str,
    context: _ProbeErrorContext,
) -> ProviderError:
    return ProviderError(
        provider_name=provider.provider_name,
        code=context.error.code,
        message=message,
        retryable=False,
        status_code=context.status_code,
        fallback_target=context.error.fallback_target,
    )


async def _probe_fallback(provider: Any, request: ChatRequest, exc: ProviderError) -> LLMResponse:
    logger.debug(
        "🤖 探测失败回退 / probe fallback: [{}] probe failed model={} base={} ({}), trying Chat Completions",
        request.source,
        request.model,
        provider._effective_base,
        exc.message,
    )
    if exc.code in {"responses_probe_unsupported", "responses_probe_prompt_ignored"}:
        set_cached_mode(provider._effective_base, "completions")
    return await provider._chat_completions(request)


def _responses_url(provider: Any) -> str:
    return f"{provider._effective_base.rstrip('/')}/responses"
