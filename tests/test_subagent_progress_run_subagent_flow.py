"""Subagent run loop flow tests: errors, artifacts, and sufficiency gates."""

import json
from unittest.mock import MagicMock

from bao.agent.run_controller import RunLoopState
from bao.agent.subagent import (
    RunRequest,
    TaskStatus,
    ToolCallExecutionRequest,
    ToolSetupResult,
)
from bao.agent.tools._coding_agent_health import CodingBackendHealth
from bao.agent.tools.registry import ToolRegistry
from bao.providers.base import LLMResponse, ToolCallRequest
from tests._subagent_progress_testkit import pytest, subagent_options

pytest_plugins = ("tests._subagent_progress_testkit",)
pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.mark.asyncio
async def test_run_subagent_tool_error_sets_last_error_and_does_not_crash(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    call_count = 0

    async def fake_chat(request):
        del request
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
    from bao.agent.subagent import SubagentManager

    manager = SubagentManager(provider, subagent_options(tmp_path, bus))
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="error-path",
        task_description="run failing tool once",
        origin={"channel": "tg", "chat_id": "1"},
    )

    await manager._run_subagent(
        RunRequest(
            task_id="t1",
            task="run failing tool once",
            label="error-path",
            origin={"channel": "tg", "chat_id": "1"},
        )
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

    state = RunLoopState(consecutive_errors=2)
    await manager._execute_tool_call_block(
        ToolCallExecutionRequest(
            task_id="t1",
            tool_call=ToolCallRequest(id="tc_interrupt", name="exec", arguments={"command": "echo 1"}),
            tools=tools,
            coding_tool=None,
            artifact_store=None,
            messages=[],
            tool_trace=[],
            sufficiency_trace=[],
            failed_directions=[],
            state=state,
        )
    )

    assert state.total_tool_steps_for_sufficiency == 1
    assert state.consecutive_errors == 0
    st = manager.get_task_status("t1")
    assert st is not None
    assert st.last_error_category is None
    assert st.last_error_code is None


@pytest.mark.asyncio
async def test_run_subagent_archives_run_artifact(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    async def fake_chat(request):
        del request
        return LLMResponse(content="done")

    provider.chat = fake_chat
    from bao.agent.subagent import SubagentManager

    manager = SubagentManager(provider, subagent_options(tmp_path, bus))
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="artifact",
        task_description="archive artifact",
        origin={"channel": "tg", "chat_id": "1"},
    )

    await manager._run_subagent(
        RunRequest(
            task_id="t1",
            task="archive artifact",
            label="artifact",
            origin={"channel": "tg", "chat_id": "1"},
        )
    )

    trajectory_dir = tmp_path / ".bao" / "context" / "subagent_t1" / "trajectory"
    files = sorted(trajectory_dir.glob("subagent_run_*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["run_kind"] == "subagent"
    assert payload["result"]["exit_reason"] == "completed"
    st = manager.get_task_status("t1")
    assert st is not None
    assert st.last_error_message is None


@pytest.mark.asyncio
async def test_run_subagent_recent_action_redacts_exec_command(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    call_count = 0

    async def fake_chat(request):
        del request
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
    from bao.agent.subagent import SubagentManager

    manager = SubagentManager(provider, subagent_options(tmp_path, bus))
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="exec",
        task_description="run command",
        origin={"channel": "tg", "chat_id": "1"},
    )

    await manager._run_subagent(
        RunRequest(
            task_id="t1",
            task="run command",
            label="exec",
            origin={"channel": "tg", "chat_id": "1"},
        )
    )

    st = manager.get_task_status("t1")
    assert st is not None
    assert any(action.startswith("exec(<redacted:") for action in st.recent_actions)


@pytest.mark.asyncio
async def test_run_subagent_sufficiency_true_disables_tools(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    call_count = 0
    final_tools = None

    async def fake_chat(request):
        nonlocal call_count, final_tools
        if request.source == "utility":
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
        final_tools = request.tools
        return LLMResponse(content="done")

    provider.chat = fake_chat
    from bao.agent.subagent import SubagentManager

    manager = SubagentManager(provider, subagent_options(tmp_path, bus))
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
    await manager._run_subagent(
        RunRequest(
            task_id="t1",
            task="run then stop",
            label="stop",
            origin={"channel": "tg", "chat_id": "1"},
        )
    )

    assert final_tools == []


@pytest.mark.asyncio
async def test_run_subagent_fails_fast_when_requested_coding_backend_unhealthy(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat = MagicMock()
    from bao.agent.subagent import SubagentManager

    manager = SubagentManager(provider, subagent_options(tmp_path, bus))
    manager._task_statuses["t1"] = TaskStatus(
        task_id="t1",
        label="codex-check",
        task_description="run codex check",
        origin={"channel": "tg", "chat_id": "1"},
    )

    class _DummyCodingTool:
        async def collect_backend_health(self, timeout_seconds: int = 20):
            del timeout_seconds
            return {
                "codex": CodingBackendHealth(
                    backend="codex",
                    ready=False,
                    error_type="model_not_available",
                    message="codex: model not available",
                    hints=("Use a supported Codex model.",),
                )
            }

    manager._setup_subagent_tools = lambda *_args, **_kwargs: ToolSetupResult(
        tools=ToolRegistry(),
        coding_tool=_DummyCodingTool(),
        coding_tools=["codex"],
        has_search=False,
        has_browser=False,
    )

    await manager._run_subagent(
        RunRequest(
            task_id="t1",
            task="请做一个 codex 链路测试",
            label="codex-check",
            origin={"channel": "tg", "chat_id": "1"},
        )
    )

    st = manager.get_task_status("t1")
    assert st is not None
    assert st.status == "failed"
    assert st.result_summary is not None
    assert "Coding backend preflight failed" in st.result_summary
    provider.chat.assert_not_called()
