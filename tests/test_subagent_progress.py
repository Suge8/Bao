"""Tests for subagent progress tracking: TaskStatus, status cache, milestone push, tools."""

import asyncio
import importlib
import time
from unittest.mock import MagicMock

from bao.agent.subagent import SubagentManager, TaskStatus
from bao.agent.tools.task_status import CancelTaskTool, CheckTasksTool, _format_status
from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus

pytest = importlib.import_module("pytest")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def manager(bus, tmp_path):
    """Create a SubagentManager with mocked provider."""
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    return SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=bus,
        model="test-model",
    )


# ---------------------------------------------------------------------------
# TaskStatus dataclass
# ---------------------------------------------------------------------------


def test_task_status_defaults():
    st = TaskStatus(
        task_id="abc",
        label="test",
        task_description="do something",
        origin={"channel": "telegram", "chat_id": "123"},
    )
    assert st.status == "running"
    assert st.iteration == 0
    assert st.max_iterations == 15
    assert st.tool_steps == 0
    assert st.phase == "starting"
    assert st.result_summary is None
    assert st.offloaded_count == 0
    assert st.offloaded_chars == 0
    assert st.clipped_count == 0
    assert st.clipped_chars == 0
    assert st.started_at > 0
    assert st.updated_at > 0


# ---------------------------------------------------------------------------
# SubagentManager: spawn creates TaskStatus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_creates_status(manager):
    """spawn() should create a TaskStatus entry and return a confirmation string."""
    result = await manager.spawn(
        task="Summarize the README",
        label="summarize",
        origin_channel="telegram",
        origin_chat_id="c1",
    )
    assert "started" in result.lower()

    statuses = manager.get_all_statuses()
    assert len(statuses) == 1
    st = statuses[0]
    assert st.label == "summarize"
    assert st.status == "running"
    assert st.task_description == "Summarize the README"
    assert st.origin == {"channel": "telegram", "chat_id": "c1"}


# ---------------------------------------------------------------------------
# SubagentManager: _update_status
# ---------------------------------------------------------------------------
def test_update_status(manager):
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="test",
        task_description="desc",
        origin={"channel": "tg", "chat_id": "1"},
    )
    manager._update_status("t1", iteration=3, phase="tool:web_fetch", tool_steps=2)
    st = manager.get_task_status("t1")
    assert st.iteration == 3
    assert st.phase == "tool:web_fetch"
    assert st.tool_steps == 2
    assert st.updated_at > st.started_at - 1  # updated_at refreshed


def test_update_status_nonexistent(manager):
    """_update_status on missing task_id should not raise."""
    manager._update_status("ghost", iteration=5)  # no error


# ---------------------------------------------------------------------------
# SubagentManager: cancel_task
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cancel_running_task(manager):
    """cancel_task should cancel the asyncio task and update status."""

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
    assert "cancelled" in result.lower()
    assert manager._task_statuses["t1"].status == "cancelled"
    assert "t1" not in manager._running_tasks


@pytest.mark.asyncio
async def test_cancel_nonexistent_task(manager):
    result = await manager.cancel_task("nope")
    assert "no running task" in result.lower()


# ---------------------------------------------------------------------------
# SubagentManager: _cleanup_completed
# ---------------------------------------------------------------------------
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
        st.updated_at = now - (55 - i)  # older tasks have smaller updated_at
        manager._task_statuses[f"t{i}"] = st
    # Add one running task — should NOT be evicted
    manager._task_statuses["running1"] = TaskStatus(
        task_id="running1",
        label="active",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
    )
    manager._cleanup_completed()
    # 50 completed remain + 1 running
    assert len(manager._task_statuses) == 51
    assert "running1" in manager._task_statuses
    # Oldest 5 should be gone (t0..t4)
    for i in range(5):
        assert f"t{i}" not in manager._task_statuses


# ---------------------------------------------------------------------------
# SubagentManager: _push_milestone
# ---------------------------------------------------------------------------
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

    await manager._push_milestone("t1", "research", 3, 15, {"channel": "tg", "chat_id": "1"})

    assert len(collected) == 1
    msg = collected[0]
    assert msg.channel == "tg"
    assert msg.chat_id == "1"
    assert "research" in msg.content
    assert "3/15" in msg.content
    assert msg.metadata.get("_progress") is True
    assert msg.metadata.get("_subagent_progress") is True
    assert msg.metadata.get("task_id") == "t1"


# ---------------------------------------------------------------------------
# _format_status helper
# ---------------------------------------------------------------------------
def test_format_status_basic():
    st = TaskStatus(
        task_id="t1",
        label="research",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        iteration=5,
        tool_steps=3,
        phase="tool:web_fetch",
    )
    out = _format_status(st)
    assert "t1" in out
    assert "research" in out
    assert "5/15" in out
    assert "3 tools" in out
    assert "tool:web_fetch" in out


def test_format_status_stale_warning():
    """Tasks with no update for >2min should show a warning."""
    st = TaskStatus(
        task_id="t1",
        label="stuck",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
        phase="thinking",
    )
    st.updated_at = time.time() - 150  # 2.5 min ago
    out = _format_status(st)
    assert "⚠️" in out
    assert "no update" in out.lower()


def test_format_status_no_warning_when_completed():
    """Completed tasks should NOT show stale warning even if updated_at is old."""
    st = TaskStatus(
        task_id="t1",
        label="done",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="completed",
        phase="completed",
    )
    st.updated_at = time.time() - 300
    out = _format_status(st)
    assert "⚠️" not in out


def test_format_status_shows_budget_metrics_when_present():
    st = TaskStatus(
        task_id="t1",
        label="budget",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
        offloaded_count=1,
        offloaded_chars=2048,
        clipped_count=2,
        clipped_chars=512,
    )
    out = _format_status(st)
    assert "budget" in out
    assert "offload 1/2048 chars" in out
    assert "clip 2/512 chars" in out


# ---------------------------------------------------------------------------
# CheckTasksTool
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# CancelTaskTool
# ---------------------------------------------------------------------------
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
    assert "cancelled" in result.lower()


# ---------------------------------------------------------------------------
# Tool schema validation
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Spawn: auto-truncate label
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_spawn_auto_label_truncation(manager):
    """When no label is given, spawn should auto-truncate task to 30 chars + '...'."""
    long_task = "A" * 50
    await manager.spawn(task=long_task)
    st = manager.get_all_statuses()[0]
    assert len(st.label) == 33  # 30 + '...'
    assert st.label.endswith("...")


# ---------------------------------------------------------------------------
# _format_status: result_summary display (bug fix verification)
# ---------------------------------------------------------------------------
def test_format_status_shows_result_summary_on_completed():
    """Completed tasks should display result_summary."""
    st = TaskStatus(
        task_id="t1",
        label="research",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="completed",
        phase="completed",
        result_summary="Found 3 relevant papers on transformer architecture.",
    )
    out = _format_status(st)
    assert "→" in out
    assert "Found 3 relevant papers" in out


def test_format_status_shows_result_summary_on_failed():
    """Failed tasks should also display result_summary."""
    st = TaskStatus(
        task_id="t1",
        label="deploy",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="failed",
        phase="failed",
        result_summary="Error: connection refused on port 5432",
    )
    out = _format_status(st)
    assert "→" in out
    assert "connection refused" in out


def test_format_status_truncates_long_summary():
    """Long result_summary should be truncated to 200 chars."""
    long_summary = "X" * 300
    st = TaskStatus(
        task_id="t1",
        label="big",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="completed",
        phase="completed",
        result_summary=long_summary,
    )
    out = _format_status(st)
    assert "..." in out
    # Should contain exactly 200 X's + '...'
    arrow_idx = out.index("→")
    summary_part = out[arrow_idx + 2 :]  # after '→ '
    assert len(summary_part.strip()) == 203  # 200 + '...'


def test_format_status_no_summary_for_running():
    """Running tasks should NOT show result_summary even if set."""
    st = TaskStatus(
        task_id="t1",
        label="active",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
        phase="thinking",
        result_summary="partial result",
    )
    out = _format_status(st)
    assert "→" not in out


# ---------------------------------------------------------------------------
# _push_milestone: tool_steps in content (bug fix verification)
# ---------------------------------------------------------------------------
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
    await manager._push_milestone("t1", "research", 6, 15, {"channel": "tg", "chat_id": "1"})
    assert len(collected) == 1
    assert "5 tools" in collected[0].content
    assert "tool:web_fetch" in collected[0].content


# ---------------------------------------------------------------------------
# spawn() empty string fallback (bug fix verification)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_spawn_empty_task_gets_fallback_label(manager):
    """spawn() with empty task string should use 'unnamed task' as label."""
    await manager.spawn(task="")
    st = manager.get_all_statuses()[0]
    assert st.label == "unnamed task"


# ---------------------------------------------------------------------------
# recent_actions: TaskStatus field + _update_status tracking
# ---------------------------------------------------------------------------
def test_task_status_recent_actions_default():
    """recent_actions should default to empty list."""
    st = TaskStatus(
        task_id="t1", label="test", task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
    )
    assert st.recent_actions == []


def test_update_status_appends_action(manager):
    """_update_status with action= should append to recent_actions."""
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1", label="test", task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
    )
    manager._update_status("t1", action="web_search(weather)")
    manager._update_status("t1", action="web_fetch(https://...)")
    st = manager.get_task_status("t1")
    assert len(st.recent_actions) == 2
    assert st.recent_actions[0] == "web_search(weather)"
    assert st.recent_actions[1] == "web_fetch(https://...)"


def test_update_status_truncates_recent_actions(manager):
    """recent_actions should be capped at _MAX_RECENT_ACTIONS."""
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1", label="test", task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
    )
    for i in range(10):
        manager._update_status("t1", action=f"tool_{i}(arg)")
    st = manager.get_task_status("t1")
    assert len(st.recent_actions) == manager._MAX_RECENT_ACTIONS
    # Should keep the LAST N actions
    assert st.recent_actions[0] == f"tool_{10 - manager._MAX_RECENT_ACTIONS}(arg)"
    assert st.recent_actions[-1] == "tool_9(arg)"


# ---------------------------------------------------------------------------
# _push_milestone: recent_actions appear in milestone content
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_push_milestone_includes_recent_actions(manager, bus):
    """_push_milestone should include last 3 recent_actions in content."""
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1", label="research", task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
    )
    # Add 4 actions — milestone should only show last 3
    for name in ["web_search(q1)", "web_fetch(url1)", "read_file(a.py)", "exec(ls)"]:
        manager._update_status("t1", action=name)
    manager._update_status("t1", iteration=3, phase="tool:exec")

    await manager._push_milestone("t1", "research", 3, 15, {"channel": "tg", "chat_id": "1"})

    msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
    assert "web_fetch(url1)" in msg.content
    assert "read_file(a.py)" in msg.content
    assert "exec(ls)" in msg.content
    # First action should NOT appear (only last 3)
    assert "web_search(q1)" not in msg.content


# ---------------------------------------------------------------------------
# _format_status: recent_actions shown for running tasks
# ---------------------------------------------------------------------------
def test_format_status_shows_recent_actions_for_running():
    """_format_status should show '→ recent:' line for running tasks with actions."""
    st = TaskStatus(
        task_id="t1", label="research", task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
    )
    st.recent_actions = ["web_search(q)", "read_file(x.py)", "exec(ls)", "write_file(out.txt)"]
    output = _format_status(st)
    assert "→ recent:" in output
    # Should show last 3 only
    assert "read_file(x.py)" in output
    assert "exec(ls)" in output
    assert "write_file(out.txt)" in output
    assert "web_search(q)" not in output


def test_format_status_no_recent_actions_for_running():
    """_format_status should NOT show '→ recent:' line when recent_actions is empty."""
    st = TaskStatus(
        task_id="t1", label="test", task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
    )
    output = _format_status(st)
    assert "→ recent:" not in output


# ---------------------------------------------------------------------------
# on_system_response callback in AgentLoop.run()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_on_system_response_fires_for_system_messages():
    """on_system_response callback should fire when run() processes a system message."""
    from bao.agent.loop import AgentLoop
    from bao.bus.events import InboundMessage, OutboundMessage

    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as td:
        loop = AgentLoop(
            bus=loop_bus, provider=provider,
            workspace=pathlib.Path(td), model="test-model",
        )

        # Track callback invocations
        captured = []

        async def fake_callback(msg: OutboundMessage):
            captured.append(msg)

        loop.on_system_response = fake_callback

        # Mock _process_message to return a response for system messages
        fake_response = OutboundMessage(
            channel="tg", chat_id="1",
            content="Subagent finished the research task."
        )

        async def fake_process(msg):
            return fake_response

        loop._process_message = fake_process
        async def _noop_mcp(): pass
        loop._connect_mcp = _noop_mcp

        # Publish a system inbound message
        await loop_bus.publish_inbound(InboundMessage(
            channel="system", sender_id="subagent",
            chat_id="tg:1", content="task done"
        ))

        # Run loop briefly — it should process the message then timeout
        loop._running = True

        async def stop_after_processing():
            await asyncio.sleep(0.2)
            loop._running = False

        asyncio.create_task(stop_after_processing())
        await loop.run()

        # Callback should have been called exactly once
        assert len(captured) == 1
        assert captured[0].content == "Subagent finished the research task."
