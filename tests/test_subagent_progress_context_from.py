"""Subagent context_from continuation behavior tests."""

import asyncio
from unittest.mock import AsyncMock, patch

from bao.agent.subagent import RunRequest, SpawnRequest, TaskStatus
from bao.providers.base import LLMResponse
from tests._subagent_progress_testkit import pytest, spawn_task_id

pytest_plugins = ("tests._subagent_progress_testkit",)
pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.mark.asyncio
async def test_spawn_context_from_completed_task(manager):
    """context_from pointing to a completed task should pass context_from to _run_subagent."""
    manager._task_statuses["prev01"] = TaskStatus(
        task_id="prev01",
        label="previous task",
        task_description="Analyze the auth module",
        origin={"channel": "hub", "chat_id": "direct"},
        status="completed",
        result_summary="Auth module uses JWT with 24h expiry.",
    )
    with patch.object(manager, "_run_subagent", new_callable=AsyncMock) as mock_run:
        result = await manager.spawn(
            SpawnRequest(
                task="Refactor auth based on previous analysis",
                label="refactor",
                context_from="prev01",
            )
        )
        assert result.status == "spawned"
        task_id = spawn_task_id(result)
        spawned = manager.get_task_status(task_id)
        assert spawned is not None
        assert spawned.resume_context is not None
        assert "Analyze the auth module" in spawned.resume_context
        assert "JWT with 24h expiry" in spawned.resume_context
        await asyncio.sleep(0.05)
        mock_run.assert_called_once()
        assert mock_run.await_args.args[0].context_from == "prev01"


@pytest.mark.asyncio
async def test_spawn_context_from_missing_task(manager):
    """context_from pointing to a non-existent task should degrade gracefully."""
    result = await manager.spawn(
        SpawnRequest(
            task="Do something new",
            label="new task",
            context_from="nonexistent",
        )
    )
    assert result.status == "spawned"
    assert result.warning is not None
    assert result.warning.code == "context_from_unavailable"
    assert len(manager.get_all_statuses()) == 1


@pytest.mark.asyncio
async def test_spawn_context_from_warning_sanitizes_visible_text(manager):
    result = await manager.spawn(
        SpawnRequest(
            task="Do something new",
            label="new task",
            context_from="bad|id\nnext",
        )
    )
    assert result.warning is not None
    assert "context_from=bad/id next" in result.warning.message
    assert "bad|id" not in result.warning.message
    assert "\n" not in result.warning.message


@pytest.mark.asyncio
async def test_spawn_context_from_running_task_ignored(manager):
    """context_from pointing to a running task should be ignored (not completed/failed)."""
    manager._task_statuses["run01"] = TaskStatus(
        task_id="run01",
        label="still running",
        task_description="Long running analysis",
        origin={"channel": "hub", "chat_id": "direct"},
        status="running",
    )
    result = await manager.spawn(
        SpawnRequest(
            task="Follow up on analysis",
            label="follow up",
            context_from="run01",
        )
    )
    assert result.status == "spawned"
    assert result.warning is not None
    assert result.warning.code == "context_from_unavailable"
    new_statuses = [s for s in manager.get_all_statuses() if s.task_id != "run01"]
    assert len(new_statuses) == 1


@pytest.mark.asyncio
async def test_context_from_injects_resume_into_messages(manager):
    """Verify that context_from actually injects resume context into provider.chat messages."""
    manager._task_statuses["done01"] = TaskStatus(
        task_id="done01",
        label="prior analysis",
        task_description="Analyze the auth module",
        origin={"channel": "hub", "chat_id": "direct"},
        status="completed",
        result_summary="Auth module uses JWT with 24h expiry.",
    )
    manager._task_statuses["new01"] = TaskStatus(
        task_id="new01",
        label="follow-up",
        task_description="Refactor auth",
        origin={"channel": "hub", "chat_id": "direct"},
    )
    captured_messages = []

    async def fake_chat(request):
        captured_messages.append(list(request.messages))
        return LLMResponse(content="Done.", tool_calls=[])

    manager.provider.chat = fake_chat
    await manager._run_subagent(
        RunRequest(
            task_id="new01",
            task="Refactor auth",
            label="follow-up",
            origin={"channel": "hub", "chat_id": "direct"},
            context_from="done01",
        )
    )
    assert len(captured_messages) >= 1
    msgs = captured_messages[0]
    assert len(msgs) >= 3
    assert msgs[1]["role"] == "user"
    assert "Continuing from previous task" in msgs[1]["content"]
    assert "Analyze the auth module" in msgs[1]["content"]
    assert "JWT with 24h expiry" in msgs[1]["content"]


@pytest.mark.asyncio
async def test_context_from_uses_snapshot_even_if_source_missing(manager):
    manager._task_statuses["new01"] = TaskStatus(
        task_id="new01",
        label="follow-up",
        task_description="Refactor auth",
        origin={"channel": "hub", "chat_id": "direct"},
        resume_context=(
            "[Continuing from previous task (done01)]\n"
            "Previous task: Analyze the auth module\n"
            "Previous result: Auth module uses JWT with 24h expiry."
        ),
    )
    captured_messages = []

    async def fake_chat(request):
        captured_messages.append(list(request.messages))
        return LLMResponse(content="Done.", tool_calls=[])

    manager.provider.chat = fake_chat
    await manager._run_subagent(
        RunRequest(
            task_id="new01",
            task="Refactor auth",
            label="follow-up",
            origin={"channel": "hub", "chat_id": "direct"},
            context_from="done01",
        )
    )

    assert len(captured_messages) >= 1
    msgs = captured_messages[0]
    assert len(msgs) >= 3
    assert msgs[1]["role"] == "user"
    assert "Continuing from previous task (done01)" in msgs[1]["content"]
