"""Spawn-related behavior: prompt assembly, task ids, context limits."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from _subagent_progress_testkit import (
    SubagentManager,
    TaskStatus,
    make_provider,
    pytest,
    spawn_task_id,
    subagent_options,
)

from bao.agent.subagent import SpawnRequest, SubagentPromptRequest
from bao.providers.base import LLMResponse
from bao.session.manager import SessionManager

pytest_plugins = ["_subagent_progress_testkit"]


@pytest.mark.asyncio
async def test_get_related_memory_uses_single_recall_path(manager: SubagentManager) -> None:
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
    provider = make_provider()
    manager = SubagentManager(
        provider,
        subagent_options(tmp_path, bus, max_iterations=7),
    )
    await manager.spawn(SpawnRequest(task="Do work", label="w"))
    st = manager.get_all_statuses()[0]
    assert st.max_iterations == 7


@pytest.mark.asyncio
async def test_spawn_persists_child_session_key(bus, tmp_path):
    provider = make_provider()
    sessions = SessionManager(tmp_path)
    manager = SubagentManager(
        provider,
        subagent_options(tmp_path, bus, sessions=sessions),
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
    provider = make_provider()
    sessions = SessionManager(tmp_path)
    manager = SubagentManager(
        provider,
        subagent_options(tmp_path, bus, sessions=sessions),
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


def test_build_subagent_prompt_includes_memory_sections(manager: SubagentManager):
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
    provider = make_provider()
    manager = SubagentManager(
        provider,
        subagent_options(tmp_path, bus),
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
    provider = make_provider()
    provider.chat = AsyncMock(return_value=LLMResponse(content='{"ok": true}'))
    manager = SubagentManager(
        provider,
        subagent_options(
            tmp_path,
            bus,
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


@pytest.mark.asyncio
async def test_spawn_creates_status(manager: SubagentManager):
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
async def test_spawn_task_id_has_12_chars(manager: SubagentManager):
    result = await manager.spawn(SpawnRequest(task="Summarize"))
    task_id = spawn_task_id(result)
    assert len(task_id) == 12
    assert "-" not in task_id


@pytest.mark.asyncio
async def test_spawn_task_id_retries_on_collision(manager: SubagentManager):
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


@pytest.mark.asyncio
async def test_spawn_auto_label_truncation(manager: SubagentManager):
    long_task = "A" * 50
    await manager.spawn(SpawnRequest(task=long_task))
    st = manager.get_all_statuses()[0]
    assert len(st.label) == 49
    assert st.label.endswith("…")


@pytest.mark.asyncio
async def test_spawn_empty_task_gets_fallback_label(manager: SubagentManager):
    await manager.spawn(SpawnRequest(task=""))
    st = manager.get_all_statuses()[0]
    assert st.label == "unnamed task"
