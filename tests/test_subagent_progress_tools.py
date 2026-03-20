"""Tools: check tasks, cancel task tool, schema validation, milestone snapshots."""

from __future__ import annotations

import asyncio
import json

from _subagent_progress_testkit import TaskStatus, pytest

from bao.agent.tools.task_status import (
    CancelTaskTool,
    CheckTasksJsonTool,
    CheckTasksTool,
)
from bao.hub import HubTaskControl, HubTaskDirectory

pytest_plugins = ["_subagent_progress_testkit"]


@pytest.mark.asyncio
async def test_check_tasks_no_tasks(manager):
    tool = CheckTasksTool(manager)
    result = await tool.execute()
    assert "no background tasks" in result.lower()


@pytest.mark.asyncio
async def test_check_tasks_single_by_id(manager):
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="research",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        iteration=3,
        phase="thinking",
    )
    tool = CheckTasksTool(manager)
    result = await tool.execute(task_id="t1")
    assert "t1" in result
    assert "research" in result


@pytest.mark.asyncio
async def test_check_tasks_not_found(manager):
    tool = CheckTasksTool(manager)
    result = await tool.execute(task_id="ghost")
    assert "no task found" in result.lower()


@pytest.mark.asyncio
async def test_check_tasks_lists_running_and_finished(manager):
    manager._task_statuses["r1"] = TaskStatus(
        task_id="r1",
        label="active",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
    )
    manager._task_statuses["f1"] = TaskStatus(
        task_id="f1",
        label="done",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="completed",
    )
    tool = CheckTasksTool(manager)
    result = await tool.execute()
    assert "running (1)" in result.lower()
    assert "finished" in result.lower()


@pytest.mark.asyncio
async def test_check_tasks_json_accepts_string_schema_version(manager):
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="research\n|task",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1", "session_key": "secret"},
        resume_context="sensitive context",
    )
    manager._task_statuses["t1"].recent_actions = ["a|b", "c\nd"]

    tool = CheckTasksJsonTool(manager)
    payload = json.loads(await tool.execute(schema_version="1"))

    assert payload["schema_version"] == 1
    assert len(payload["tasks"]) == 1
    snap = payload["tasks"][0]
    assert snap["task_id"] == "t1"
    assert snap["child_session_key"] is None
    assert snap["label"] == "research /task"
    assert snap["recent_actions"] == ["a/b", "c d"]
    assert snap["origin"] == {"channel": "tg", "chat_id": "1"}
    assert "resume_context" not in snap
    assert "task_description" not in snap


@pytest.mark.asyncio
async def test_check_tasks_json_includes_child_session_key(manager):
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="research",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        child_session_key="subagent:desktop:local::main::t1",
    )

    tool = CheckTasksJsonTool(manager)
    payload = json.loads(await tool.execute(task_id="t1"))

    assert payload["tasks"][0]["child_session_key"] == "subagent:desktop:local::main::t1"


@pytest.mark.asyncio
async def test_check_tasks_json_rejects_blank_task_id(manager):
    tool = CheckTasksJsonTool(manager)
    payload = json.loads(await tool.execute(task_id="   "))
    assert payload["schema_version"] == 1
    assert payload["error"]["code"] == "invalid_task_id"


@pytest.mark.asyncio
async def test_check_tasks_json_rejects_non_integer_schema_version(manager):
    tool = CheckTasksJsonTool(manager)
    payload = json.loads(await tool.execute(schema_version="not-a-number"))
    assert payload["schema_version"] == 1
    assert payload["error"]["code"] == "invalid_schema_version"


@pytest.mark.asyncio
async def test_check_tasks_json_unsupported_schema_version(manager):
    tool = CheckTasksJsonTool(manager)
    payload = json.loads(await tool.execute(schema_version=2))
    assert payload["schema_version"] == 1
    assert payload["error"]["code"] == "unsupported_schema_version"


@pytest.mark.asyncio
async def test_cancel_task_tool(manager):
    async def _hang():
        await asyncio.sleep(3600)

    bg = asyncio.create_task(_hang())
    manager._running_tasks["t1"] = bg
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="hang",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
    )
    tool = CancelTaskTool(manager)
    result = await tool.execute(task_id="t1")
    assert "cancellation requested" in result.lower()
    with pytest.raises(asyncio.CancelledError):
        await bg


def test_check_tasks_tool_schema(manager):
    tool = CheckTasksTool(manager)
    assert tool.name == "check_tasks"
    schema = tool.to_schema()
    assert schema["function"]["name"] == "check_tasks"
    assert "task_id" in schema["function"]["parameters"]["properties"]


def test_cancel_task_tool_schema(manager):
    tool = CancelTaskTool(manager)
    assert tool.name == "cancel_task"
    schema = tool.to_schema()
    assert "task_id" in schema["function"]["parameters"]["required"]


@pytest.mark.asyncio
async def test_check_tasks_tool_accepts_hub_task_directory(manager):
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="research",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
    )
    tool = CheckTasksTool(HubTaskDirectory(manager))

    result = await tool.execute(task_id="t1")

    assert "t1" in result
    assert "research" in result


@pytest.mark.asyncio
async def test_cancel_task_tool_accepts_hub_task_control(manager):
    async def _hang():
        await asyncio.sleep(3600)

    bg = asyncio.create_task(_hang())
    manager._running_tasks["t1"] = bg
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="hang",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
    )
    tool = CancelTaskTool(HubTaskControl(manager))

    result = await tool.execute(task_id="t1")

    assert "cancellation requested" in result.lower()
    with pytest.raises(asyncio.CancelledError):
        await bg
