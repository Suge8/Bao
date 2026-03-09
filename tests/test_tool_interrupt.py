"""Tests for in-flight tool cancellation via soft interrupt."""

import asyncio
import importlib

pytest = importlib.import_module("pytest")
pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.mark.asyncio
async def test_await_tool_with_interrupt_cancels_long_tool():
    """When soft interrupt is set, _await_tool_with_interrupt cancels the tool task."""
    from bao.agent.loop import AgentLoop

    loop = AgentLoop.__new__(AgentLoop)
    loop._interrupted_tasks = set()

    cancelled = asyncio.Event()

    async def long_tool():
        try:
            await asyncio.sleep(60)
            return "should not reach"
        except asyncio.CancelledError:
            cancelled.set()
            raise

    tool_task = asyncio.create_task(long_tool())
    run_task = asyncio.current_task()
    assert run_task is not None

    async def interrupt_after_start():
        await asyncio.sleep(0.05)
        loop._interrupted_tasks.add(run_task)

    asyncio.create_task(interrupt_after_start())

    result = await loop._await_tool_with_interrupt(tool_task, run_task)

    assert result == "Cancelled by soft interrupt."
    assert cancelled.is_set()
    assert tool_task.done()


@pytest.mark.asyncio
async def test_await_tool_with_interrupt_no_interrupt_returns_normally():
    """Without interrupt, tool result passes through unchanged."""
    from bao.agent.loop import AgentLoop

    loop = AgentLoop.__new__(AgentLoop)
    loop._interrupted_tasks = set()

    async def quick_tool():
        return "tool output"

    tool_task = asyncio.create_task(quick_tool())
    run_task = asyncio.current_task()

    result = await loop._await_tool_with_interrupt(tool_task, run_task)
    assert result == "tool output"


@pytest.mark.asyncio
async def test_await_tool_with_interrupt_outer_cancel_cleans_up():
    """Outer CancelledError propagates after cleaning up tool task."""
    from bao.agent.loop import AgentLoop

    loop = AgentLoop.__new__(AgentLoop)
    loop._interrupted_tasks = set()

    async def long_tool():
        await asyncio.sleep(60)
        return "nope"

    tool_task = asyncio.create_task(long_tool())
    run_task = asyncio.current_task()

    wrapper = asyncio.create_task(loop._await_tool_with_interrupt(tool_task, run_task))
    await asyncio.sleep(0.05)
    wrapper.cancel()

    with pytest.raises(asyncio.CancelledError):
        await wrapper

    # tool_task must also be cleaned up
    assert tool_task.done()


@pytest.mark.asyncio
async def test_await_tool_with_interrupt_swallowed_cancel_bounded_wait():
    """Tool that swallows CancelledError still returns within _TOOL_CANCEL_TIMEOUT."""
    from bao.agent.loop import AgentLoop

    loop = AgentLoop.__new__(AgentLoop)
    loop._interrupted_tasks = set()

    async def stubborn_tool():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            await asyncio.sleep(60)  # swallow and hang
            return "swallowed"
        return "unreachable"

    tool_task = asyncio.create_task(stubborn_tool())
    run_task = asyncio.current_task()
    assert run_task is not None

    async def interrupt_after_start():
        await asyncio.sleep(0.05)
        loop._interrupted_tasks.add(run_task)

    asyncio.create_task(interrupt_after_start())

    import time

    t0 = time.monotonic()
    result = await loop._await_tool_with_interrupt(tool_task, run_task)
    elapsed = time.monotonic() - t0

    assert result == "Cancelled by soft interrupt."
    # Must not hang 60s; bounded by _TOOL_CANCEL_TIMEOUT
    assert elapsed < loop._TOOL_CANCEL_TIMEOUT + 1.0
