"""Tests for subagent progress tracking: TaskStatus, status cache, milestone push, tools."""

import asyncio
import importlib
import json
import pathlib
import tempfile
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch

from bao.agent.subagent import SpawnResult, SubagentManager, TaskStatus
from bao.agent.tools.registry import ToolRegistry
from bao.agent.tools.task_status import (
    CancelTaskTool,
    CheckTasksJsonTool,
    CheckTasksTool,
    _format_brief,
    _format_detailed,
)
from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.providers.base import LLMResponse, ToolCallRequest
from bao.session.manager import SessionManager

pytest = importlib.import_module("pytest")
pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _spawn_task_id(result: SpawnResult) -> str:
    assert result.task is not None
    return result.task.task_id


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
    assert st.max_iterations == 20
    assert st.tool_steps == 0
    assert st.phase == "starting"
    assert st.result_summary is None
    assert st.offloaded_count == 0
    assert st.offloaded_chars == 0
    assert st.clipped_count == 0
    assert st.clipped_chars == 0
    assert st.started_at > 0
    assert st.updated_at > 0


@pytest.mark.asyncio
async def test_spawn_uses_configured_max_iterations(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    manager = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=bus,
        model="test-model",
        max_iterations=7,
    )
    await manager.spawn(task="Do work", label="w")
    st = manager.get_all_statuses()[0]
    assert st.max_iterations == 7


@pytest.mark.asyncio
async def test_spawn_persists_child_session_key(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    sessions = SessionManager(tmp_path)
    manager = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=bus,
        model="test-model",
        sessions=sessions,
    )

    result = await manager.spawn(
        task="Research topic",
        label="research",
        session_key="desktop:local::main",
    )

    assert result.task is not None
    assert result.task.child_session_key is not None
    assert result.task.child_session_key.startswith("subagent:desktop:local::main::")
    status = manager.get_all_statuses()[0]
    assert status.child_session_key is not None


@pytest.mark.asyncio
async def test_spawn_rejects_unknown_child_session_key(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    sessions = SessionManager(tmp_path)
    manager = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=bus,
        model="test-model",
        sessions=sessions,
    )

    result = await manager.spawn(
        task="Continue thread",
        session_key="desktop:local::main",
        child_session_key="subagent:desktop:local::main::missing",
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "unknown_child_session_key"


def test_build_subagent_prompt_includes_memory_sections(manager):
    prompt = manager._build_subagent_prompt(
        "task",
        channel="telegram",
        has_search=True,
        has_browser=True,
        related_memory=["pref: use concise replies"],
        related_experience=["lesson: verify with tests"],
    )
    assert "## Related Memory" in prompt
    assert "## Past Experience" in prompt
    assert "Control a browser" in prompt
    assert "built-in skills:" in prompt
    assert "workspace overrides:" in prompt


def test_build_subagent_prompt_points_coding_skill_to_builtin_path(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    manager = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=bus,
        model="test-model",
    )

    prompt = manager._build_subagent_prompt("task", channel="telegram", coding_tools=["opencode"])

    assert "`bao/skills/coding-agent/SKILL.md`" in prompt
    assert (
        "If the task matches a skill in those locations, read that `SKILL.md` before any substantive action."
        in prompt
    )


@pytest.mark.asyncio
async def test_call_experience_llm_utility_mode_falls_back_to_main(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat = AsyncMock(return_value=LLMResponse(content='{"ok": true}'))
    manager = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=bus,
        model="test-model",
        experience_mode="utility",
    )

    result = await manager._call_experience_llm("system", "prompt")
    assert result == {"ok": True}
    provider.chat.assert_awaited_once()
    assert provider.chat.await_args.kwargs["source"] == "utility"


def test_subagent_error_detection_avoids_no_errors_false_positive():
    assert not SubagentManager._has_tool_error(
        "web_search", "How to fix failed login error in Django"
    )
    assert SubagentManager._has_tool_error("web_search", "Error: provider timeout")
    assert SubagentManager._has_tool_error(
        "web_fetch", '{"error": "URL validation failed: Missing domain"}'
    )
    assert SubagentManager._has_tool_error("exec", "Error: permission denied")


def test_subagent_error_detection_exec_exit_code_marker():
    assert SubagentManager._has_tool_error("exec", "stdout\nExit code: 1\n")


def test_subagent_error_detection_coding_agent_json_status():
    assert SubagentManager._has_tool_error("coding_agent", '{"status":"error","exit_code":1}')


def test_subagent_error_detection_coding_agent_prefixed_json():
    payload = 'summary: {"status":"error","exitCode":1}'
    assert SubagentManager._has_tool_error("coding_agent", payload)


@pytest.mark.asyncio
async def test_run_subagent_tool_error_sets_last_error_and_does_not_crash(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    call_count = 0

    async def fake_chat(*, messages, **kwargs):
        del messages, kwargs
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="tc_1",
                        name="exec",
                        arguments={"command": 'python -c "import sys; sys.exit(1)"'},
                    )
                ],
            )
        return LLMResponse(content="done")

    provider.chat = fake_chat
    manager = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=bus,
        model="test-model",
    )
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="error-path",
        task_description="run failing tool once",
        origin={"channel": "tg", "chat_id": "1"},
    )

    await manager._run_subagent(
        "t1", "run failing tool once", "error-path", {"channel": "tg", "chat_id": "1"}
    )

    st = manager.get_task_status("t1")
    assert st is not None
    assert st.status == "completed"
    assert st.last_error_category == "execution_error"
    assert st.last_error_code == "exec_exit_code"
    assert isinstance(st.last_error_message, str)
    assert st.last_error_message


@pytest.mark.asyncio
async def test_execute_tool_call_block_interrupted_resets_consecutive_errors(manager):
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="interrupt",
        task_description="interrupt edge",
        origin={"channel": "tg", "chat_id": "1"},
    )

    tools = ToolRegistry()

    async def _fake_execute(name, params):
        del name, params
        return "Cancelled by soft interrupt."

    tools.execute = _fake_execute

    tool_step, consecutive_errors = await manager._execute_tool_call_block(
        task_id="t1",
        tool_call=ToolCallRequest(id="tc_interrupt", name="exec", arguments={"command": "echo 1"}),
        tools=tools,
        coding_tool=None,
        artifact_store=None,
        messages=[],
        tool_trace=[],
        sufficiency_trace=[],
        failed_directions=[],
        tool_step=0,
        consecutive_errors=2,
    )

    assert tool_step == 1
    assert consecutive_errors == 0
    st = manager.get_task_status("t1")
    assert st is not None
    assert st.last_error_category is None
    assert st.last_error_code is None
    assert st.last_error_message is None


def test_subagent_strip_think_matches_main_behavior():
    assert SubagentManager._strip_think("<think>hidden</think> visible") == "visible"
    assert SubagentManager._strip_think("<think>only hidden</think>") is None


@pytest.mark.asyncio
async def test_run_subagent_recent_action_redacts_exec_command(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    call_count = 0

    async def fake_chat(*, messages, **kwargs):
        del messages, kwargs
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="tc_1",
                        name="exec",
                        arguments={"command": "echo super-secret-token"},
                    )
                ],
            )
        return LLMResponse(content="done")

    provider.chat = fake_chat
    manager = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=bus,
        model="test-model",
    )
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="exec",
        task_description="run command",
        origin={"channel": "tg", "chat_id": "1"},
    )

    await manager._run_subagent("t1", "run command", "exec", {"channel": "tg", "chat_id": "1"})

    st = manager.get_task_status("t1")
    assert st is not None
    assert any(action.startswith("exec(<redacted:") for action in st.recent_actions)


@pytest.mark.asyncio
async def test_run_subagent_sufficiency_true_disables_tools(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    call_count = 0
    final_tools = None

    async def fake_chat(*, messages, **kwargs):
        del messages
        nonlocal call_count, final_tools
        if kwargs.get("source") == "utility":
            return LLMResponse(content='{"sufficient": false}')
        if call_count < 8:
            call_count += 1
            return LLMResponse(
                content=f"step-{call_count}",
                tool_calls=[
                    ToolCallRequest(
                        id=f"tc_{call_count}",
                        name="exec",
                        arguments={"command": 'python -c "print(1)"'},
                    )
                ],
            )
        final_tools = kwargs.get("tools")
        return LLMResponse(content="done")

    provider.chat = fake_chat
    manager = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=bus,
        model="test-model",
    )
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="stop",
        task_description="run then stop",
        origin={"channel": "tg", "chat_id": "1"},
    )

    async def fake_check(
        user_request: str, trace: list[str], last_state_text: str | None = None
    ) -> bool:
        del user_request, trace, last_state_text
        return True

    setattr(manager, "_check_sufficiency", fake_check)
    await manager._run_subagent("t1", "run then stop", "stop", {"channel": "tg", "chat_id": "1"})

    assert final_tools == []


@pytest.mark.asyncio
async def test_run_subagent_empty_final_allows_one_tool_backoff(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    call_count = 0
    empty_final_sent = False
    tools_history: list[object] = []

    async def fake_chat(*, messages, **kwargs):
        del messages
        nonlocal call_count, empty_final_sent
        tools_history.append(kwargs.get("tools", "__missing__"))
        if kwargs.get("source") == "utility":
            return LLMResponse(content='{"sufficient": false}')
        if call_count < 2:
            call_count += 1
            return LLMResponse(
                content=f"step-{call_count}",
                tool_calls=[
                    ToolCallRequest(
                        id=f"tc_{call_count}_{idx}",
                        name="exec",
                        arguments={"command": 'python -c "print(1)"'},
                    )
                    for idx in range(4)
                ],
            )
        if not empty_final_sent:
            empty_final_sent = True
            return LLMResponse(content="")
        return LLMResponse(content="done")

    provider.chat = fake_chat
    manager = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=bus,
        model="test-model",
    )
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="backoff",
        task_description="backoff test",
        origin={"channel": "tg", "chat_id": "1"},
    )

    async def fake_check(
        user_request: str, trace: list[str], last_state_text: str | None = None
    ) -> bool:
        del user_request, trace, last_state_text
        return True

    setattr(manager, "_check_sufficiency", fake_check)
    await manager._run_subagent("t1", "backoff test", "backoff", {"channel": "tg", "chat_id": "1"})

    assert [] in tools_history
    empty_idx = tools_history.index([])
    assert any(t not in ([], None, "__missing__") for t in tools_history[empty_idx + 1 :])


@pytest.mark.asyncio
async def test_run_subagent_sufficiency_uses_trace_window(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    call_count = 0

    async def fake_chat(*, messages, **kwargs):
        del messages, kwargs
        nonlocal call_count
        if call_count < 9:
            call_count += 1
            return LLMResponse(
                content=f"step-{call_count}",
                tool_calls=[
                    ToolCallRequest(
                        id=f"tc_{call_count}",
                        name="exec",
                        arguments={"command": 'python -c "print(1)"'},
                    )
                ],
            )
        return LLMResponse(content="done")

    provider.chat = fake_chat
    manager = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=bus,
        model="test-model",
    )
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="trace",
        task_description="trace window",
        origin={"channel": "tg", "chat_id": "1"},
    )
    captured_lengths: list[int] = []

    async def fake_check(
        user_request: str, trace: list[str], last_state_text: str | None = None
    ) -> bool:
        del user_request, last_state_text
        captured_lengths.append(len(trace))
        return False

    setattr(manager, "_check_sufficiency", fake_check)
    await manager._run_subagent("t1", "trace window", "trace", {"channel": "tg", "chat_id": "1"})

    assert captured_lengths
    assert captured_lengths[0] >= 8


@pytest.mark.asyncio
async def test_run_subagent_allows_write_when_path_not_first_arg(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    captured_messages = []
    call_count = 0

    async def fake_chat(*, messages, **kwargs):
        del kwargs
        nonlocal call_count
        call_count += 1
        captured_messages.append(list(messages))
        if call_count == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="tc_1",
                        name="write_file",
                        arguments={"content": "secret", "path": "lancedb/data.arrow"},
                    )
                ],
            )
        return LLMResponse(content="done")

    provider.chat = fake_chat
    manager = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=bus,
        model="test-model",
    )
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="write",
        task_description="try write",
        origin={"channel": "tg", "chat_id": "1"},
    )

    await manager._run_subagent("t1", "write task", "write", {"channel": "tg", "chat_id": "1"})

    assert (tmp_path / "lancedb" / "data.arrow").exists()


@pytest.mark.asyncio
async def test_run_subagent_allows_exec_command_touching_protected_paths(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    captured_messages = []
    call_count = 0

    async def fake_chat(*, messages, **kwargs):
        del kwargs
        nonlocal call_count
        call_count += 1
        captured_messages.append(list(messages))
        if call_count == 1:
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="tc_exec_1",
                        name="exec",
                        arguments={"command": "ls memory || true"},
                    )
                ],
            )
        return LLMResponse(content="done")

    provider.chat = fake_chat
    manager = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=bus,
        model="test-model",
    )
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="exec",
        task_description="try exec",
        origin={"channel": "tg", "chat_id": "1"},
    )

    await manager._run_subagent("t1", "exec task", "exec", {"channel": "tg", "chat_id": "1"})

    assert len(captured_messages) >= 2
    tool_msgs = [m for m in captured_messages[1] if m.get("role") == "tool"]
    assert tool_msgs
    assert (
        "exec access to protected paths is blocked"
        not in str(tool_msgs[-1].get("content", "")).lower()
    )


def test_redact_tool_args_for_log_hides_write_contents(manager):
    redacted = manager._redact_tool_args_for_log(
        "write_file",
        {"path": "src/a.py", "content": "secret", "old_text": "abc", "new_text": "xyz"},
    )
    payload = json.loads(redacted)
    assert payload["path"] == "src/a.py"
    assert payload["content"] == "<redacted:6 chars>"
    assert payload["old_text"] == "<redacted:3 chars>"
    assert payload["new_text"] == "<redacted:3 chars>"


def test_redact_tool_args_for_log_hides_exec_command(manager):
    redacted = manager._redact_tool_args_for_log(
        "exec",
        {"command": "echo secret", "timeout": 5},
    )
    payload = json.loads(redacted)
    assert payload["command"] == "<redacted:11 chars>"
    assert payload["timeout"] == 5


@pytest.mark.asyncio
async def test_run_subagent_keeps_artifacts_after_completion(bus, tmp_path, monkeypatch):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat = AsyncMock(return_value=LLMResponse(content="done"))
    manager = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=bus,
        model="test-model",
        context_management="auto",
    )
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="check",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
    )

    cleanup_called = False

    def _mark_cleanup(_self):
        nonlocal cleanup_called
        cleanup_called = True

    monkeypatch.setattr("bao.agent.artifacts.ArtifactStore.cleanup_session", _mark_cleanup)
    await manager._run_subagent("t1", "simple task", "check", {"channel": "tg", "chat_id": "1"})

    assert cleanup_called is False
    status = manager.get_task_status("t1")
    assert status is not None
    assert status.status == "completed"


@pytest.mark.asyncio
async def test_run_subagent_keeps_completed_status_when_announce_fails(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat = AsyncMock(return_value=LLMResponse(content="done"))
    manager = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=bus,
        model="test-model",
    )
    manager.bus.publish_inbound = AsyncMock(side_effect=RuntimeError("bus down"))
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="check",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
    )

    await manager._run_subagent("t1", "simple task", "check", {"channel": "tg", "chat_id": "1"})

    status = manager.get_task_status("t1")
    assert status is not None
    assert status.status == "completed"


# ---------------------------------------------------------------------------
# SubagentManager: spawn creates TaskStatus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_creates_status(manager):
    result = await manager.spawn(
        task="Summarize the README",
        label="summarize",
        origin_channel="telegram",
        origin_chat_id="c1",
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
    result = await manager.spawn(task="Summarize")
    task_id = _spawn_task_id(result)
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
        "bao.agent.subagent.uuid.uuid4",
        side_effect=[
            uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        ],
    ):
        result = await manager.spawn(task="Summarize")
    task_id = _spawn_task_id(result)
    assert task_id == "bbbbbbbbbbbb"


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
    out = _format_detailed(st)
    assert "t1" in out
    assert "research" in out
    assert "5/20" in out
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
    out = _format_detailed(st)
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
    out = _format_brief(st)
    assert "⚠️" not in out


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
    assert "cancellation requested" in result.lower()
    with pytest.raises(asyncio.CancelledError):
        await bg


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
    """When no label is given, spawn should auto-truncate task to 48 chars + '…'."""
    long_task = "A" * 50
    await manager.spawn(task=long_task)
    st = manager.get_all_statuses()[0]
    assert len(st.label) == 49  # 48 + '…'
    assert st.label.endswith("…")


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
    out = _format_detailed(st)
    assert "result:" in out
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
    out = _format_detailed(st)
    assert "result:" in out
    assert "connection refused" in out


def test_format_status_truncates_long_summary():
    """Long result_summary should be truncated to 300 chars."""
    long_summary = "X" * 400
    st = TaskStatus(
        task_id="t1",
        label="big",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="completed",
        phase="completed",
        result_summary=long_summary,
    )
    out = _format_detailed(st)
    assert "..." in out
    # Should contain exactly 300 X's + '...'
    result_idx = out.index("result:")
    summary_part = out[result_idx + 8 :]  # after 'result: '
    assert summary_part.strip().startswith("X" * 300)
    assert summary_part.strip().endswith("...")


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
    out = _format_brief(st)
    assert "result:" not in out


def test_format_status_sanitizes_pipe_in_result_summary():
    st = TaskStatus(
        task_id="t1",
        label="report",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="completed",
        phase="completed",
        result_summary="A|B|C",
    )
    out = _format_brief(st)
    assert "A/B/C" in out
    assert "A|B|C" not in out


def test_format_status_sanitizes_pipe_in_recent_actions():
    st = TaskStatus(
        task_id="t1",
        label="running",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
    )
    st.recent_actions = ["exec(ls|wc)"]
    out = _format_detailed(st)
    assert "exec(ls/wc)" in out
    assert "exec(ls|wc)" not in out


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
    await manager._push_milestone(
        "t1", "research", 6, manager.max_iterations, {"channel": "tg", "chat_id": "1"}
    )
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
    manager._update_status("t1", action="web_search(weather)")
    manager._update_status("t1", action="web_fetch(https://...)")
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
        task_id="t1",
        label="research",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
    )
    # Add 4 actions — milestone should only show last 3
    for name in ["web_search(q1)", "web_fetch(url1)", "read_file(a.py)", "exec(ls)"]:
        manager._update_status("t1", action=name)
    manager._update_status("t1", iteration=3, phase="tool:exec")

    await manager._push_milestone(
        "t1", "research", 3, manager.max_iterations, {"channel": "tg", "chat_id": "1"}
    )

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
    """_format_detailed should show 'recent:' line for running tasks with actions."""
    st = TaskStatus(
        task_id="t1",
        label="research",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
    )
    st.recent_actions = ["web_search(q)", "read_file(x.py)", "exec(ls)", "write_file(out.txt)"]
    output = _format_detailed(st)
    assert "recent:" in output
    # Should show last 3 only
    assert "read_file(x.py)" in output
    assert "exec(ls)" in output
    assert "write_file(out.txt)" in output
    assert "web_search(q)" not in output


def test_format_status_no_recent_actions_for_running():
    """_format_detailed should NOT show 'recent:' line when recent_actions is empty."""
    st = TaskStatus(
        task_id="t1",
        label="test",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
    )
    output = _format_detailed(st)
    assert "recent:" not in output


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
    with tempfile.TemporaryDirectory() as td:
        loop = AgentLoop(
            bus=loop_bus,
            provider=provider,
            workspace=pathlib.Path(td),
            model="test-model",
        )

        # Track callback invocations
        captured = []

        async def fake_callback(msg: OutboundMessage):
            captured.append(msg)

        loop.on_system_response = fake_callback

        # Mock _process_message to return a response for system messages
        fake_response = OutboundMessage(
            channel="tg", chat_id="1", content="Subagent finished the research task."
        )

        async def fake_process(
            msg,
            session_key=None,
            on_progress=None,
            on_event=None,
            expected_generation=None,
            expected_generation_key=None,
        ):
            del (
                msg,
                session_key,
                on_progress,
                on_event,
                expected_generation,
                expected_generation_key,
            )
            return fake_response

        loop._process_message = fake_process

        async def _noop_mcp():
            pass

        loop._connect_mcp = _noop_mcp

        # Publish a system inbound message
        await loop_bus.publish_inbound(
            InboundMessage(
                channel="system", sender_id="subagent", chat_id="tg:1", content="task done"
            )
        )

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


@pytest.mark.asyncio
async def test_system_response_preserves_session_key_metadata():
    from bao.agent.loop import AgentLoop
    from bao.bus.events import InboundMessage, OutboundMessage

    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with tempfile.TemporaryDirectory() as td:
        loop = AgentLoop(
            bus=loop_bus,
            provider=provider,
            workspace=pathlib.Path(td),
            model="test-model",
        )

        captured: list[OutboundMessage] = []

        async def fake_callback(msg: OutboundMessage):
            captured.append(msg)

        loop.on_system_response = fake_callback

        async def fake_run_agent_loop(*args, **kwargs):
            del args, kwargs
            return "done", [], [], 0, []

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)

        def _search_memory(query: str, limit: int = 5) -> list[str]:
            del query, limit
            return []

        def _search_experience(query: str, limit: int = 3) -> list[str]:
            del query, limit
            return []

        loop.context.memory.search_memory = _search_memory
        loop.context.memory.search_experience = _search_experience

        async def _noop_mcp():
            pass

        loop._connect_mcp = _noop_mcp

        await loop_bus.publish_inbound(
            InboundMessage(
                channel="system",
                sender_id="subagent",
                chat_id="tg:1",
                content="",
                metadata={
                    "session_key": "tg:1::s2",
                    "origin": "test",
                    "system_event": {
                        "type": "subagent_result",
                        "task_id": "task-1",
                        "label": "research",
                        "task": "research topic",
                        "status": "ok",
                        "result": "done",
                    },
                },
            )
        )

        loop._running = True

        async def stop_after_processing():
            await asyncio.sleep(0.2)
            loop._running = False

        asyncio.create_task(stop_after_processing())
        await loop.run()

        assert len(captured) == 1
        assert captured[0].metadata.get("session_key") == "tg:1::s2"
        assert captured[0].metadata.get("origin") == "test"
        assert "system_event" not in captured[0].metadata


@pytest.mark.asyncio
async def test_announce_result_publishes_structured_system_event(manager):
    manager.bus.publish_inbound = AsyncMock()

    await manager._announce_result(
        "task123",
        "research",
        "look into memory flow",
        "Found the duplication path.",
        {"channel": "desktop", "chat_id": "local", "session_key": "desktop:local"},
        "ok",
    )

    manager.bus.publish_inbound.assert_awaited_once()
    await_args = manager.bus.publish_inbound.await_args
    assert await_args is not None
    inbound = await_args.args[0]
    assert inbound.channel == "system"
    assert inbound.sender_id == "subagent"
    assert inbound.content == ""
    assert inbound.metadata["session_key"] == "desktop:local"
    assert inbound.metadata["system_event"] == {
        "type": "subagent_result",
        "task_id": "task123",
        "label": "research",
        "task": "look into memory flow",
        "status": "ok",
        "result": "Found the duplication path.",
    }


def test_shared_subagent_result_event_helpers_normalize_contract():
    from bao.agent import shared

    event = shared.build_subagent_result_event(
        task_id=" task123 ",
        label=" research ",
        task=" look into memory flow ",
        status="unexpected",
        result=" done ",
    )

    assert event == {
        "type": "subagent_result",
        "task_id": "task123",
        "label": "research",
        "task": "look into memory flow",
        "status": "ok",
        "result": "done",
    }
    parsed = shared.parse_subagent_result_event({"system_event": event})
    assert parsed == event


@pytest.mark.asyncio
async def test_handle_stop_cancels_natural_and_active_session_subagents():
    from bao.agent.loop import AgentLoop
    from bao.bus.events import InboundMessage

    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with tempfile.TemporaryDirectory() as td:
        loop = AgentLoop(
            bus=loop_bus,
            provider=provider,
            workspace=pathlib.Path(td),
            model="test-model",
        )

        natural_key = "telegram:1"
        active_key = "telegram:1::s2"
        loop.sessions.set_active_session_key(natural_key, active_key)

        loop.subagents.cancel_by_session = AsyncMock(return_value=0)

        await loop._handle_stop(
            InboundMessage(
                channel="telegram",
                sender_id="user",
                chat_id="1",
                content="/stop",
            )
        )

        assert loop.subagents.cancel_by_session.await_args_list == [
            call(natural_key, wait=False),
            call(active_key, wait=False),
        ]


# ---------------------------------------------------------------------------
# context_from: subagent session continuation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_context_from_completed_task(manager):
    """context_from pointing to a completed task should pass context_from to _run_subagent."""
    manager._task_statuses["prev01"] = TaskStatus(
        task_id="prev01",
        label="previous task",
        task_description="Analyze the auth module",
        origin={"channel": "gateway", "chat_id": "direct"},
        status="completed",
        result_summary="Auth module uses JWT with 24h expiry.",
    )
    with patch.object(manager, "_run_subagent", new_callable=AsyncMock) as mock_run:
        result = await manager.spawn(
            task="Refactor auth based on previous analysis",
            label="refactor",
            context_from="prev01",
        )
        assert result.status == "spawned"
        task_id = _spawn_task_id(result)
        spawned = manager.get_task_status(task_id)
        assert spawned is not None
        assert spawned.resume_context is not None
        assert "Analyze the auth module" in spawned.resume_context
        assert "JWT with 24h expiry" in spawned.resume_context
        # Wait for asyncio.create_task to schedule the call
        await asyncio.sleep(0.05)
        mock_run.assert_called_once()
        # context_from is the 5th positional arg (task_id, task, label, origin, context_from)
        assert mock_run.call_args[0][4] == "prev01"


@pytest.mark.asyncio
async def test_spawn_context_from_missing_task(manager):
    """context_from pointing to a non-existent task should degrade gracefully."""
    result = await manager.spawn(
        task="Do something new",
        label="new task",
        context_from="nonexistent",
    )
    assert result.status == "spawned"
    assert result.warning is not None
    assert result.warning.code == "context_from_unavailable"
    assert len(manager.get_all_statuses()) == 1


@pytest.mark.asyncio
async def test_spawn_context_from_warning_sanitizes_visible_text(manager):
    result = await manager.spawn(
        task="Do something new",
        label="new task",
        context_from="bad|id\nnext",
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
        origin={"channel": "gateway", "chat_id": "direct"},
        status="running",
    )
    result = await manager.spawn(
        task="Follow up on analysis",
        label="follow up",
        context_from="run01",
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
        origin={"channel": "gateway", "chat_id": "direct"},
        status="completed",
        result_summary="Auth module uses JWT with 24h expiry.",
    )
    # Create a new task entry so _run_subagent can update it
    manager._task_statuses["new01"] = TaskStatus(
        task_id="new01",
        label="follow-up",
        task_description="Refactor auth",
        origin={"channel": "gateway", "chat_id": "direct"},
    )
    # Mock provider.chat to capture messages and return final answer
    captured_messages = []

    async def fake_chat(*, messages, **kwargs):
        captured_messages.append(list(messages))
        return LLMResponse(content="Done.", tool_calls=[])

    manager.provider.chat = fake_chat
    await manager._run_subagent(
        "new01",
        "Refactor auth",
        "follow-up",
        {"channel": "gateway", "chat_id": "direct"},
        context_from="done01",
    )
    assert len(captured_messages) >= 1
    msgs = captured_messages[0]
    # messages: [system, resume_context, user_task]
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
        origin={"channel": "gateway", "chat_id": "direct"},
        resume_context=(
            "[Continuing from previous task (done01)]\n"
            "Previous task: Analyze the auth module\n"
            "Previous result: Auth module uses JWT with 24h expiry."
        ),
    )
    captured_messages = []

    async def fake_chat(*, messages, **kwargs):
        captured_messages.append(list(messages))
        return LLMResponse(content="Done.", tool_calls=[])

    manager.provider.chat = fake_chat
    await manager._run_subagent(
        "new01",
        "Refactor auth",
        "follow-up",
        {"channel": "gateway", "chat_id": "direct"},
        context_from="done01",
    )

    assert len(captured_messages) >= 1
    msgs = captured_messages[0]
    assert len(msgs) >= 3
    assert msgs[1]["role"] == "user"
    assert "Continuing from previous task (done01)" in msgs[1]["content"]
