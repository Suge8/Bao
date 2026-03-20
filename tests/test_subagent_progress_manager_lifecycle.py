"""Subagent manager lifecycle tests: spawn/update/cancel/cleanup/milestone."""

import asyncio
import time
import uuid
from unittest.mock import patch

from bao.agent.subagent import SpawnRequest, StatusUpdate, TaskStatus
from tests._subagent_progress_testkit import pytest, spawn_task_id

pytest_plugins = ("tests._subagent_progress_testkit",)
pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.mark.asyncio
async def test_spawn_creates_status(manager):
    result = await manager.spawn(
        SpawnRequest(
            task="Summarize the README",
            label="summarize",
            origin_channel="telegram",
            origin_chat_id="c1",
        )
    )
    assert result.status == "spawned"
    assert result.task is not None

    statuses = manager.get_all_statuses()
    assert len(statuses) == 1
    st = statuses[0]
    assert st.label == "summarize"
    assert st.status == "running"
    assert st.task_description == "Summarize the README"
    assert st.origin == {"channel": "telegram", "chat_id": "c1"}


@pytest.mark.asyncio
async def test_spawn_task_id_has_12_chars(manager):
    result = await manager.spawn(SpawnRequest(task="Summarize"))
    task_id = spawn_task_id(result)
    assert len(task_id) == 12
    assert "-" not in task_id


@pytest.mark.asyncio
async def test_spawn_task_id_retries_on_collision(manager):
    manager._task_statuses["aaaaaaaaaaaa"] = TaskStatus(
        task_id="aaaaaaaaaaaa",
        label="existing",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
    )
    with patch(
        "bao.agent._subagent_status_spawn.uuid.uuid4",
        side_effect=[
            uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        ],
    ):
        result = await manager.spawn(SpawnRequest(task="Summarize"))
    task_id = spawn_task_id(result)
    assert task_id == "bbbbbbbbbbbb"


def test_update_status(manager):
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="test",
        task_description="desc",
        origin={"channel": "tg", "chat_id": "1"},
    )
    manager._update_status(
        StatusUpdate(task_id="t1", iteration=3, phase="tool:web_fetch", tool_steps=2)
    )
    st = manager.get_task_status("t1")
    assert st.iteration == 3
    assert st.phase == "tool:web_fetch"
    assert st.tool_steps == 2
    assert st.updated_at > st.started_at - 1


def test_update_status_nonexistent(manager):
    """_update_status on missing task_id should not raise."""
    manager._update_status(StatusUpdate(task_id="ghost", iteration=5))


@pytest.mark.asyncio
async def test_cancel_running_task(manager):
    async def _hang():
        await asyncio.sleep(3600)

    bg = asyncio.create_task(_hang())
    manager._running_tasks["t1"] = bg
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="hang",
        task_description="hang forever",
        origin={"channel": "tg", "chat_id": "1"},
    )
    result = await manager.cancel_task("t1")
    assert "cancellation requested" in result.lower()
    assert manager._task_statuses["t1"].status == "running"
    assert manager._task_statuses["t1"].phase == "cancel_requested"
    assert "t1" in manager._running_tasks
    with pytest.raises(asyncio.CancelledError):
        await bg


@pytest.mark.asyncio
async def test_cancel_task_does_not_override_completed_status(manager):
    async def _hang():
        await asyncio.sleep(3600)

    bg = asyncio.create_task(_hang())
    manager._running_tasks["t1"] = bg
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="done",
        task_description="already done",
        origin={"channel": "tg", "chat_id": "1"},
        status="completed",
    )

    result = await manager.cancel_task("t1")
    assert "cancellation requested" in result.lower()
    assert manager._task_statuses["t1"].status == "completed"

    with pytest.raises(asyncio.CancelledError):
        await bg


@pytest.mark.asyncio
async def test_cancel_nonexistent_task(manager):
    result = await manager.cancel_task("nope")
    assert "no running task" in result.lower()


def test_cleanup_completed_under_limit(manager):
    """No cleanup when finished count <= _MAX_COMPLETED."""
    for i in range(10):
        manager._task_statuses[f"t{i}"] = TaskStatus(
            task_id=f"t{i}",
            label=f"done-{i}",
            task_description="d",
            origin={"channel": "tg", "chat_id": "1"},
            status="completed",
        )
    manager._cleanup_completed()
    assert len(manager._task_statuses) == 10


def test_cleanup_completed_over_limit(manager):
    """Oldest finished tasks evicted when count > _MAX_COMPLETED."""
    now = time.time()
    for i in range(55):
        st = TaskStatus(
            task_id=f"t{i}",
            label=f"done-{i}",
            task_description="d",
            origin={"channel": "tg", "chat_id": "1"},
            status="completed",
        )
        st.updated_at = now - (55 - i)
        manager._task_statuses[f"t{i}"] = st
    manager._task_statuses["running1"] = TaskStatus(
        task_id="running1",
        label="active",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
    )
    manager._cleanup_completed()
    assert len(manager._task_statuses) == 51
    assert "running1" in manager._task_statuses
    for i in range(5):
        assert f"t{i}" not in manager._task_statuses


@pytest.mark.asyncio
async def test_spawn_auto_label_truncation(manager):
    """When no label is given, spawn should auto-truncate task to 48 chars + '…'."""
    long_task = "A" * 50
    await manager.spawn(SpawnRequest(task=long_task))
    st = manager.get_all_statuses()[0]
    assert len(st.label) == 49
    assert st.label.endswith("…")


@pytest.mark.asyncio
async def test_spawn_empty_task_gets_fallback_label(manager):
    """spawn() with empty task string should use 'unnamed task' as label."""
    await manager.spawn(SpawnRequest(task=""))
    st = manager.get_all_statuses()[0]
    assert st.label == "unnamed task"


def test_task_status_recent_actions_default():
    """recent_actions should default to empty list."""
    st = TaskStatus(
        task_id="t1",
        label="test",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
    )
    assert st.recent_actions == []


def test_update_status_appends_action(manager):
    """_update_status with action= should append to recent_actions."""
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="test",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
    )
    manager._update_status(StatusUpdate(task_id="t1", action="web_search(weather)"))
    manager._update_status(StatusUpdate(task_id="t1", action="web_fetch(https://...)"))
    st = manager.get_task_status("t1")
    assert len(st.recent_actions) == 2
    assert st.recent_actions[0] == "web_search(weather)"
    assert st.recent_actions[1] == "web_fetch(https://...)"


def test_update_status_truncates_recent_actions(manager):
    """recent_actions should be capped at _MAX_RECENT_ACTIONS."""
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="test",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
    )
    for i in range(10):
        manager._update_status(StatusUpdate(task_id="t1", action=f"tool_{i}(arg)"))
    st = manager.get_task_status("t1")
    assert len(st.recent_actions) == manager._MAX_RECENT_ACTIONS
    assert st.recent_actions[0] == f"tool_{10 - manager._MAX_RECENT_ACTIONS}(arg)"
    assert st.recent_actions[-1] == "tool_9(arg)"
