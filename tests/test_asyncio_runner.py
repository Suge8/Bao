"""Tests for AsyncioRunner."""

from __future__ import annotations

import asyncio
import importlib

from app.backend.asyncio_runner import AsyncioRunner

pytest = importlib.import_module("pytest")
pytestmark = pytest.mark.unit


@pytest.fixture
def runner():
    r = AsyncioRunner()
    r.start()
    yield r
    r.shutdown(grace_s=3.0)


@pytest.mark.smoke
def test_submit_and_get_result(runner):
    async def add(a, b):
        return a + b

    fut = runner.submit(add(2, 3))
    assert fut.result(timeout=3) == 5


def test_submit_exception_propagates(runner):
    async def boom():
        raise ValueError("test error")

    fut = runner.submit(boom())
    with pytest.raises(ValueError, match="test error"):
        fut.result(timeout=3)


@pytest.mark.smoke
def test_shutdown_does_not_hang(runner):
    async def slow():
        await asyncio.sleep(0.1)
        return "ok"

    fut = runner.submit(slow())
    runner.shutdown(grace_s=3.0)
    # After shutdown, future should still resolve
    assert fut.result(timeout=3) == "ok"


def test_submit_after_shutdown_raises():
    r = AsyncioRunner()
    r.start()
    r.shutdown(grace_s=3.0)
    coro = asyncio.sleep(0)
    with pytest.raises(RuntimeError):
        r.submit(coro)
    coro.close()


def test_start_idempotent():
    r = AsyncioRunner()
    r.start()
    r.start()  # second call should be no-op
    fut = r.submit(asyncio.sleep(0))
    fut.result(timeout=3)
    r.shutdown()


def test_submit_before_start_raises():
    r = AsyncioRunner()
    coro = asyncio.sleep(0)
    with pytest.raises(RuntimeError):
        r.submit(coro)
    coro.close()


def test_run_user_io_supports_kwargs(runner):
    async def call():
        return await runner.run_user_io(lambda *, value: value, value="ok")

    fut = runner.submit(call())
    assert fut.result(timeout=3) == "ok"
