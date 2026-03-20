from __future__ import annotations

from types import SimpleNamespace

import pytest

from bao.providers.base import LLMResponse
from bao.providers.openai_provider import OpenAICompatibleProvider
from bao.providers.retry import StreamInterruptedError
from bao.providers.runtime import (
    ProviderExecutionRequest,
    ProviderRuntimeExecutor,
    provider_error_from_exception,
)

pytestmark = pytest.mark.unit


class _StatusError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.response = SimpleNamespace(status_code=status_code, headers={})


def test_provider_error_from_exception_keeps_status_code() -> None:
    error = provider_error_from_exception("openai", _StatusError("service unavailable", 503))

    assert error.provider_name == "openai"
    assert error.status_code == 503
    assert error.retryable is True


def test_openai_capability_snapshot_reports_runtime_modes() -> None:
    provider = OpenAICompatibleProvider(api_key="k", api_base="https://x.com/v1")

    snapshot = provider.get_capability_snapshot("gpt-5")

    assert snapshot.provider_name == provider.provider_name
    assert snapshot.supported_api_modes == ("responses", "completions")
    assert snapshot.supports_reasoning_effort is True
    assert snapshot.supports_service_tier is True


@pytest.mark.asyncio
async def test_provider_runtime_executor_maps_stream_interrupt_to_interrupted_response() -> None:
    executor = ProviderRuntimeExecutor("gemini")

    async def _run() -> LLMResponse:
        raise StreamInterruptedError("soft interrupt")

    result = await executor.run(
        _run,
        ProviderExecutionRequest(
            error_prefix="Error calling Gemini",
            progress_error_prefix="Error calling Gemini progress callback",
        ),
    )

    assert isinstance(result, LLMResponse)
    assert result.finish_reason == "interrupted"
