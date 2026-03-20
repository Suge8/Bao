"""Core subagent progress tests: status defaults, prompt, error detection."""

import json
from unittest.mock import AsyncMock, MagicMock

from bao.agent.subagent import (
    SpawnRequest,
    SubagentManager,
    SubagentManagerOptions,
    SubagentPromptRequest,
    TaskStatus,
)
from bao.providers.base import LLMResponse
from bao.session.manager import SessionManager
from tests._subagent_progress_testkit import pytest

pytest_plugins = ("tests._subagent_progress_testkit",)
pytestmark = [pytest.mark.integration, pytest.mark.slow]


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
async def test_get_related_memory_uses_single_recall_path(manager) -> None:
    class _FakeMemory:
        def recall(self, query: str, **kwargs):
            assert query == "do work"
            assert kwargs["related_limit"] == 3
            assert kwargs["experience_limit"] == 3
            assert kwargs["include_long_term"] is False
            return type(
                "_Bundle",
                (),
                {
                    "related_memory": ("mem-1",),
                    "related_experience": ("exp-1",),
                },
            )()

    manager._memory = _FakeMemory()

    mem, exp = await manager._get_related_memory("do work")

    assert mem == ["mem-1"]
    assert exp == ["exp-1"]


@pytest.mark.asyncio
async def test_spawn_uses_configured_max_iterations(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    manager = SubagentManager(
        provider,
        SubagentManagerOptions(workspace=tmp_path, bus=bus, model="test-model", max_iterations=7),
    )
    await manager.spawn(SpawnRequest(task="Do work", label="w"))
    st = manager.get_all_statuses()[0]
    assert st.max_iterations == 7


@pytest.mark.asyncio
async def test_spawn_persists_child_session_key(bus, tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    sessions = SessionManager(tmp_path)
    manager = SubagentManager(
        provider,
        SubagentManagerOptions(workspace=tmp_path, bus=bus, model="test-model", sessions=sessions),
    )

    result = await manager.spawn(
        SpawnRequest(
            task="Research topic",
            label="research",
            session_key="desktop:local::main",
        )
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
        provider,
        SubagentManagerOptions(workspace=tmp_path, bus=bus, model="test-model", sessions=sessions),
    )

    result = await manager.spawn(
        SpawnRequest(
            task="Continue thread",
            session_key="desktop:local::main",
            child_session_key="subagent:desktop:local::main::missing",
        )
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "unknown_child_session_key"
    assert "omit child_session_key" in result.error.message
    assert "task.task_id" in result.error.message


def test_build_subagent_prompt_includes_memory_sections(manager):
    prompt = manager._build_subagent_prompt(
        SubagentPromptRequest(
            task="task",
            channel="telegram",
            has_search=True,
            has_browser=True,
            related_memory=["pref: use concise replies"],
            related_experience=["lesson: verify with tests"],
        )
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
        provider,
        SubagentManagerOptions(workspace=tmp_path, bus=bus, model="test-model"),
    )

    prompt = manager._build_subagent_prompt(
        SubagentPromptRequest(task="task", channel="telegram", coding_tools=["opencode"])
    )

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
        provider,
        SubagentManagerOptions(
            workspace=tmp_path,
            bus=bus,
            model="test-model",
            experience_mode="utility",
            service_tier="priority",
        ),
    )

    result = await manager._call_experience_llm("system", "prompt")
    assert result == {"ok": True}
    provider.chat.assert_awaited_once()
    request = provider.chat.await_args.args[0]
    assert request.source == "utility"
    assert request.service_tier == "priority"


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


def test_subagent_strip_think_matches_main_behavior():
    assert SubagentManager._strip_think("<think>hidden</think> visible") == "visible"
    assert SubagentManager._strip_think("<think>only hidden</think>") is None


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
