from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from bao.agent.context import ContextBuilder, SystemPromptRequest
from bao.agent.loop import AgentLoop
from bao.bus.queue import MessageBus


def _make_builder(tmp_path: Path) -> ContextBuilder:
    _ = (tmp_path / "PERSONA.md").write_text("# Persona\n", encoding="utf-8")
    _ = (tmp_path / "INSTRUCTIONS.md").write_text("# Instructions\n", encoding="utf-8")
    return ContextBuilder(tmp_path)


def test_identity_contract_is_injected_into_system_prompt(tmp_path: Path) -> None:
    builder = _make_builder(tmp_path)

    prompt = builder.build_system_prompt(SystemPromptRequest(channel="desktop", chat_id="user"))

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

    prompt = builder.build_system_prompt(SystemPromptRequest(channel="desktop", chat_id="user"))

    assert "## Runtime (actual host)" in prompt
    assert "Host:" in prompt
    assert "Channel: desktop | Chat: user" in prompt


def test_available_now_block_can_be_injected_into_system_prompt(tmp_path: Path) -> None:
    builder = _make_builder(tmp_path)

    prompt = builder.build_system_prompt(SystemPromptRequest(channel="desktop", chat_id="user"))
    prompt = builder.apply_available_tools_block(
        prompt,
        ["- web_search: Search the web for fresh information."],
    )

    assert "## Available Now" in prompt
    assert "web_search" in prompt
    assert "current tools as the source of truth" in prompt
    assert "first use session discovery tools to resolve a target session/ref" in prompt
    assert "Runtime handles target-side receipt and result routing" in prompt


def test_skills_prompt_mentions_workspace_and_builtin_skill_paths(tmp_path: Path) -> None:
    builder = _make_builder(tmp_path)

    prompt = builder.build_system_prompt(SystemPromptRequest(channel="desktop", chat_id="user"))

    assert "Before any substantive action, check whether the task matches a skill" in prompt
    assert "reading its `SKILL.md` before acting is mandatory" in prompt
    assert (
        "If multiple skills match, read the most specific domain- or format-specific skill first"
        in prompt
    )
    assert "If the request explicitly names a framework, file type, platform, or domain" in prompt
    assert "Use the matching skill entry's `path` as the exact `read_file` argument." in prompt
    assert "The index already resolves workspace overrides" in prompt
    assert (
        'If `available="false"`, that skill\'s dependencies are not currently available' in prompt
    )


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

        prompt = builder.build_system_prompt(SystemPromptRequest(channel="desktop", chat_id="user"))
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


def test_build_system_prompt_reuses_cached_bootstrap_files(tmp_path: Path) -> None:
    builder = _make_builder(tmp_path)
    builder.skills.get_always_skills = lambda: []  # type: ignore[method-assign]
    builder.skills.build_skills_summary = lambda: ""  # type: ignore[method-assign]

    prompt = builder.build_system_prompt(SystemPromptRequest(channel="desktop", chat_id="user"))
    assert "# Persona" in prompt
    assert "# Instructions" in prompt

    original_read_text = Path.read_text

    def _fail_bootstrap_reads(self: Path, *args, **kwargs) -> str:
        if self.name in {"PERSONA.md", "INSTRUCTIONS.md"}:
            raise AssertionError("bootstrap files should be served from cache")
        return original_read_text(self, *args, **kwargs)

    with patch.object(Path, "read_text", _fail_bootstrap_reads):
        cached_prompt = builder.build_system_prompt(SystemPromptRequest(channel="desktop", chat_id="user"))

    assert cached_prompt == prompt

    _ = (tmp_path / "PERSONA.md").write_text("# Persona v2\n", encoding="utf-8")
    refreshed = builder.build_system_prompt(SystemPromptRequest(channel="desktop", chat_id="user"))
    assert "# Persona v2" in refreshed


def test_build_system_prompt_invalidates_bootstrap_cache_when_stat_signature_changes(
    tmp_path: Path,
) -> None:
    builder = _make_builder(tmp_path)
    builder.skills.get_always_skills = lambda: []  # type: ignore[method-assign]
    builder.skills.build_skills_summary = lambda: ""  # type: ignore[method-assign]

    first = builder.build_system_prompt(SystemPromptRequest(channel="desktop", chat_id="user"))
    assert "# Persona\n" in first

    persona_path = tmp_path / "PERSONA.md"
    original_read_text = Path.read_text
    original_stat = Path.stat
    current_stat = persona_path.stat()
    updated_text = "# Persona changed\n"

    def _patched_stat(self: Path):
        if self == persona_path:
            return SimpleNamespace(
                st_mtime_ns=current_stat.st_mtime_ns,
                st_ctime_ns=current_stat.st_ctime_ns + 1,
                st_size=len(updated_text.encode("utf-8")),
            )
        return original_stat(self)

    def _patched_read_text(self: Path, *args, **kwargs) -> str:
        if self == persona_path:
            return updated_text
        return original_read_text(self, *args, **kwargs)

    with (
        patch.object(Path, "stat", _patched_stat),
        patch.object(Path, "read_text", _patched_read_text),
    ):
        refreshed = builder.build_system_prompt(SystemPromptRequest(channel="desktop", chat_id="user"))

    assert "# Persona changed" in refreshed
