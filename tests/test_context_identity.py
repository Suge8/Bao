from pathlib import Path
from unittest.mock import MagicMock, patch

from bao.agent.context import ContextBuilder
from bao.agent.loop import AgentLoop
from bao.bus.queue import MessageBus


def _make_builder(tmp_path: Path) -> ContextBuilder:
    _ = (tmp_path / "PERSONA.md").write_text("# Persona\n", encoding="utf-8")
    _ = (tmp_path / "INSTRUCTIONS.md").write_text("# Instructions\n", encoding="utf-8")
    return ContextBuilder(tmp_path)


def test_identity_contract_is_injected_into_system_prompt(tmp_path: Path) -> None:
    builder = _make_builder(tmp_path)

    prompt = builder.build_system_prompt(channel="desktop", chat_id="user")

    assert "## Identity Contract" in prompt
    assert "Canonical identity: You are Bao." in prompt
    assert "if PERSONA defines your name/nickname" in prompt
    assert "Identity answers must be concise" in prompt
    assert "update PERSONA.md via edit_file" in prompt
    assert "Do not present yourself as another assistant/product" in prompt
    assert "Follow PERSONA.md as your primary style/identity guidance" in prompt
    assert "Follow INSTRUCTIONS.md as user instructions" in prompt


def test_runtime_block_remains_present_with_identity_contract(tmp_path: Path) -> None:
    builder = _make_builder(tmp_path)

    prompt = builder.build_system_prompt(channel="desktop", chat_id="user")

    assert "## Runtime (actual host)" in prompt
    assert "Host:" in prompt
    assert "Channel: desktop | Chat: user" in prompt


def test_available_now_block_can_be_injected_into_system_prompt(tmp_path: Path) -> None:
    builder = _make_builder(tmp_path)

    prompt = builder.build_system_prompt(channel="desktop", chat_id="user")
    prompt = builder.apply_available_tools_block(
        prompt,
        ["- web_search: Search the web for fresh information."],
    )

    assert "## Available Now" in prompt
    assert "web_search" in prompt
    assert "current tools as the source of truth" in prompt


def test_skills_prompt_mentions_workspace_and_builtin_skill_paths(tmp_path: Path) -> None:
    builder = _make_builder(tmp_path)

    prompt = builder.build_system_prompt(channel="desktop", chat_id="user")

    assert "workspace skills: `skills/{name}/SKILL.md`" in prompt
    assert "built-in skills: `bao/skills/{name}/SKILL.md`" in prompt


def test_context_builder_defers_memory_store_until_first_memory_access(tmp_path: Path) -> None:
    init_calls = 0

    class FakeMemoryStore:
        def __init__(self, workspace: Path, embedding_config=None) -> None:
            nonlocal init_calls
            init_calls += 1
            self.workspace = workspace
            self.embedding_config = embedding_config

        def get_relevant_memory_context(self, *_args, **_kwargs) -> str:
            return ""

        def search_memory(self, *_args, **_kwargs) -> list[str]:
            return ["mem"]

        def search_experience(self, *_args, **_kwargs) -> list[str]:
            return ["exp"]

    with patch("bao.agent.context.MemoryStore", FakeMemoryStore):
        builder = _make_builder(tmp_path)
        assert init_calls == 0

        prompt = builder.build_system_prompt(channel="desktop", chat_id="user")
        assert "## Identity Contract" in prompt
        assert init_calls == 0

        assert builder.memory.search_memory("hello") == ["mem"]
        assert builder.memory.search_experience("hello") == ["exp"]
        assert init_calls == 1


def test_agent_loop_construction_keeps_memory_lazy(tmp_path: Path) -> None:
    init_calls = 0

    class FakeMemoryStore:
        def __init__(self, workspace: Path, embedding_config=None) -> None:
            nonlocal init_calls
            init_calls += 1
            self.workspace = workspace
            self.embedding_config = embedding_config

        def get_relevant_memory_context(self, *_args, **_kwargs) -> str:
            return ""

        def search_memory(self, *_args, **_kwargs) -> list[str]:
            return []

        def search_experience(self, *_args, **_kwargs) -> list[str]:
            return []

    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with patch("bao.agent.context.MemoryStore", FakeMemoryStore):
        loop = AgentLoop(
            bus=MessageBus(),
            provider=provider,
            workspace=tmp_path,
            model="test-model",
        )
        assert init_calls == 0

        assert loop.context.memory.search_memory("hello") == []
        assert init_calls == 1
