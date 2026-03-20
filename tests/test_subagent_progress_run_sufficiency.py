"""Subagent run loop sufficiency and safety behaviors (split from run mega-file)."""

from __future__ import annotations

from _subagent_progress_testkit import add_task, make_provider, pytest

from bao.agent.subagent import RunRequest, SubagentManager
from bao.providers.base import LLMResponse, ToolCallRequest
from tests._subagent_progress_testkit import subagent_options

pytest_plugins = ["_subagent_progress_testkit"]


@pytest.mark.asyncio
async def test_run_subagent_sufficiency_true_disables_tools(bus, tmp_path):
    provider = make_provider()

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
    manager = SubagentManager(provider, subagent_options(tmp_path, bus))
    add_task(
        manager,
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
async def test_run_subagent_empty_final_allows_one_tool_backoff(bus, tmp_path):
    provider = make_provider()

    call_count = 0
    empty_final_sent = False
    tools_history: list[object] = []

    async def fake_chat(request):
        nonlocal call_count, empty_final_sent
        tools_history.append(request.tools if request.tools is not None else "__missing__")
        if request.source == "utility":
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
    manager = SubagentManager(provider, subagent_options(tmp_path, bus))
    add_task(
        manager,
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
    await manager._run_subagent(
        RunRequest(
            task_id="t1",
            task="backoff test",
            label="backoff",
            origin={"channel": "tg", "chat_id": "1"},
        )
    )

    assert [] in tools_history
    empty_idx = tools_history.index([])
    assert any(t not in ([], None, "__missing__") for t in tools_history[empty_idx + 1 :])


@pytest.mark.asyncio
async def test_run_subagent_sufficiency_uses_trace_window(bus, tmp_path):
    provider = make_provider()

    call_count = 0

    async def fake_chat(request):
        del request
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
    manager = SubagentManager(provider, subagent_options(tmp_path, bus))
    add_task(
        manager,
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
    await manager._run_subagent(
        RunRequest(
            task_id="t1",
            task="trace window",
            label="trace",
            origin={"channel": "tg", "chat_id": "1"},
        )
    )

    assert captured_lengths
    assert captured_lengths[0] >= 8


@pytest.mark.asyncio
async def test_run_subagent_allows_write_when_path_not_first_arg(bus, tmp_path):
    provider = make_provider()

    captured_messages = []
    call_count = 0

    async def fake_chat(request):
        nonlocal call_count
        call_count += 1
        captured_messages.append(list(request.messages))
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
    manager = SubagentManager(provider, subagent_options(tmp_path, bus))
    add_task(
        manager,
        task_id="t1",
        label="write",
        task_description="try write",
        origin={"channel": "tg", "chat_id": "1"},
    )

    await manager._run_subagent(
        RunRequest(
            task_id="t1",
            task="write task",
            label="write",
            origin={"channel": "tg", "chat_id": "1"},
        )
    )

    assert (tmp_path / "lancedb" / "data.arrow").exists()


@pytest.mark.asyncio
async def test_run_subagent_allows_exec_command_touching_protected_paths(bus, tmp_path):
    provider = make_provider()

    captured_messages = []
    call_count = 0

    async def fake_chat(request):
        nonlocal call_count
        call_count += 1
        captured_messages.append(list(request.messages))
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
    manager = SubagentManager(provider, subagent_options(tmp_path, bus))
    add_task(
        manager,
        task_id="t1",
        label="exec",
        task_description="try exec",
        origin={"channel": "tg", "chat_id": "1"},
    )

    await manager._run_subagent(
        RunRequest(
            task_id="t1",
            task="exec task",
            label="exec",
            origin={"channel": "tg", "chat_id": "1"},
        )
    )

    assert len(captured_messages) >= 2
    tool_msgs = [m for m in captured_messages[1] if m.get("role") == "tool"]
    assert tool_msgs
    assert (
        "exec access to protected paths is blocked"
        not in str(tool_msgs[-1].get("content", "")).lower()
    )
