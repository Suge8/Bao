"""Subagent milestone message composition tests."""

import asyncio

from bao.agent.subagent import StatusUpdate, TaskStatus
from bao.bus.events import OutboundMessage
from tests._subagent_progress_testkit import pytest

pytest_plugins = ("tests._subagent_progress_testkit",)
pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.mark.asyncio
async def test_push_milestone_publishes_outbound(manager, bus):
    """_push_milestone should publish an OutboundMessage with progress metadata."""
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="research",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        phase="tool:web_fetch",
    )
    collected: list[OutboundMessage] = []
    original_publish = bus.publish_outbound

    async def _capture(msg):
        collected.append(msg)
        await original_publish(msg)

    bus.publish_outbound = _capture

    await manager._push_milestone(
        "t1", "research", 3, manager.max_iterations, {"channel": "tg", "chat_id": "1"}
    )

    assert len(collected) == 1
    msg = collected[0]
    assert msg.channel == "tg"
    assert msg.chat_id == "1"
    assert "research" in msg.content
    assert f"3/{manager.max_iterations}" in msg.content
    assert msg.metadata.get("_progress") is True
    assert msg.metadata.get("_subagent_progress") is True
    assert msg.metadata.get("_progress_scope") == "subagent:t1"
    assert msg.metadata.get("task_id") == "t1"


@pytest.mark.asyncio
async def test_push_milestone_includes_tool_steps(manager, bus):
    """Milestone message should include tool_steps count."""
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="research",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        phase="tool:web_fetch",
        tool_steps=5,
    )
    collected: list[OutboundMessage] = []
    original_publish = bus.publish_outbound

    async def _capture(msg):
        collected.append(msg)
        await original_publish(msg)

    bus.publish_outbound = _capture
    await manager._push_milestone(
        "t1", "research", 6, manager.max_iterations, {"channel": "tg", "chat_id": "1"}
    )
    assert len(collected) == 1
    assert "5 tools" in collected[0].content
    assert "tool:web_fetch" in collected[0].content


@pytest.mark.asyncio
async def test_push_milestone_includes_recent_actions(manager, bus):
    """_push_milestone should include last 3 recent_actions in content."""
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="research",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
    )
    for name in ["web_search(q1)", "web_fetch(url1)", "read_file(a.py)", "exec(ls)"]:
        manager._update_status(StatusUpdate(task_id="t1", action=name))
    manager._update_status(StatusUpdate(task_id="t1", iteration=3, phase="tool:exec"))

    await manager._push_milestone(
        "t1", "research", 3, manager.max_iterations, {"channel": "tg", "chat_id": "1"}
    )

    msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
    assert "web_fetch(url1)" in msg.content
    assert "read_file(a.py)" in msg.content
    assert "exec(ls)" in msg.content
    assert "web_search(q1)" not in msg.content
