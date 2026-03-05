from pathlib import Path

from bao.agent.context import ContextBuilder


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
