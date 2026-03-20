# ruff: noqa: F403, F405
from __future__ import annotations

from tests._channel_lifecycle_testkit import *


@pytest.mark.asyncio
async def test_base_reconnect_loop_retries_after_failure() -> None:
    channel = _DummyChannel()
    channel._start_lifecycle()
    attempts = 0

    async def _run_once() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("boom")
        channel._stop_lifecycle()

    await channel._run_reconnect_loop(_run_once, label="dummy", delay_s=0.01)

    assert attempts == 2


@pytest.mark.asyncio
async def test_base_reconnect_loop_delay_wakes_on_stop() -> None:
    channel = _DummyChannel()
    channel._start_lifecycle()
    calls = 0

    async def _run_once() -> None:
        nonlocal calls
        calls += 1

    task = asyncio.create_task(channel._run_reconnect_loop(_run_once, label="dummy", delay_s=60))
    await asyncio.sleep(0)
    channel._stop_lifecycle()
    await asyncio.wait_for(task, timeout=0.5)

    assert calls == 1


@pytest.mark.asyncio
async def test_base_stop_lifecycle_is_idempotent() -> None:
    channel = _DummyChannel()
    channel._start_lifecycle()

    channel._stop_lifecycle()
    channel._stop_lifecycle()

    assert channel._running is False
    assert channel._stop_event is not None and channel._stop_event.is_set()
