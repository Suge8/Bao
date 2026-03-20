from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar

from bao.providers.base import LLMResponse
from bao.providers.retry import (
    DEFAULT_BASE_DELAY,
    DEFAULT_MAX_RETRIES,
    ProgressCallbackError,
    RetryRunOptions,
    StreamInterruptedError,
    run_with_retries,
    safe_error_text,
    should_retry_exception,
)

_T = TypeVar("_T")


@dataclass(frozen=True)
class ProviderError(Exception):
    provider_name: str
    code: str
    message: str
    retryable: bool | None = None
    status_code: int | None = None
    fallback_target: str = ""
    cause: BaseException | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class ProviderRetryPolicy:
    max_retries: int = DEFAULT_MAX_RETRIES
    base_delay: float = DEFAULT_BASE_DELAY


@dataclass(frozen=True)
class ProviderErrorContext:
    code: str = "provider_error"
    fallback_target: str = ""


@dataclass(frozen=True)
class ProviderExecutionRequest:
    error_prefix: str
    progress_error_prefix: str
    retry_policy: ProviderRetryPolicy | None = None
    on_retry: Callable[[BaseException, int, float], Awaitable[None] | None] | None = None
    fallback: Callable[[ProviderError], Awaitable[_T]] | None = None
    should_fallback: Callable[[ProviderError], bool] | None = None
    error_code: str = "provider_error"


def provider_error_from_exception(
    provider_name: str,
    exc: BaseException,
    context: ProviderErrorContext | None = None,
) -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    error_context = context or ProviderErrorContext()
    status_code = _extract_status_code(exc)
    return ProviderError(
        provider_name=provider_name,
        code=error_context.code,
        message=safe_error_text(exc),
        retryable=should_retry_exception(exc),
        status_code=status_code,
        fallback_target=error_context.fallback_target,
        cause=exc,
    )


def progress_callback_error_response(
    exc: ProgressCallbackError,
    *,
    progress_error_prefix: str,
    partial_content: str | None = None,
) -> LLMResponse:
    if isinstance(exc, StreamInterruptedError):
        return LLMResponse(content=partial_content or None, finish_reason="interrupted")
    cause = exc.__cause__ or exc
    return LLMResponse(
        content=f"{progress_error_prefix}: {safe_error_text(cause)}",
        finish_reason="error",
    )


class ProviderRuntimeExecutor:
    def __init__(
        self,
        provider_name: str,
        *,
        partial_content: Callable[[], str | None] | None = None,
    ) -> None:
        self._provider_name = provider_name
        self._partial_content = partial_content

    async def run(
        self,
        operation: Callable[[], Awaitable[_T]],
        request: ProviderExecutionRequest,
    ) -> _T | LLMResponse:
        try:
            if request.retry_policy is None:
                return await operation()
            return await run_with_retries(
                operation,
                RetryRunOptions(
                    max_retries=request.retry_policy.max_retries,
                    base_delay=request.retry_policy.base_delay,
                    on_retry=request.on_retry,
                ),
            )
        except asyncio.CancelledError:
            raise
        except ProgressCallbackError as exc:
            return progress_callback_error_response(
                exc,
                progress_error_prefix=request.progress_error_prefix,
                partial_content=self._partial_content() if self._partial_content else None,
            )
        except Exception as exc:
            provider_error = provider_error_from_exception(
                self._provider_name,
                exc,
                ProviderErrorContext(code=request.error_code),
            )
            if request.fallback is not None and (
                request.should_fallback(provider_error) if request.should_fallback else True
            ):
                return await request.fallback(provider_error)
            return LLMResponse(
                content=f"{request.error_prefix}: {provider_error.message}",
                finish_reason="error",
            )


def _extract_status_code(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None
