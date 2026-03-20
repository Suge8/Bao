# ruff: noqa: F403, F405
from __future__ import annotations

from tests._provider_retry_testkit import *


@pytest.mark.smoke
def test_retry_helper_status_and_retry_after() -> None:
    retryable = _ResponseError("service unavailable", 503)
    non_retryable = _ResponseError("unauthorized", 401)
    retry_after = _ResponseError("rate limit", 429, retry_after="5")

    assert should_retry_exception(retryable)
    assert not should_retry_exception(non_retryable)
    assert compute_retry_delay(retry_after, attempt=0, base_delay=1.0) == 5.0


@pytest.mark.smoke
def test_run_with_retries_retries_until_success() -> None:
    attempts = {"count": 0}

    async def _op() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("connection reset by peer")
        return "ok"

    result = asyncio.run(run_with_retries(_op, RetryRunOptions(max_retries=2, base_delay=0.01)))

    assert result == "ok"
    assert attempts["count"] == 2


@pytest.mark.smoke
def test_run_with_retries_stops_on_non_retryable_error() -> None:
    attempts = {"count": 0}

    async def _op() -> str:
        attempts["count"] += 1
        raise _ResponseError("unauthorized", 401)

    with pytest.raises(_ResponseError):
        asyncio.run(run_with_retries(_op, RetryRunOptions(max_retries=2, base_delay=0.01)))

    assert attempts["count"] == 1
