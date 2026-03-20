# ruff: noqa: F403, F405
from __future__ import annotations

from tests._compress_audit_testkit import *


@pytest.mark.asyncio
async def test_sufficiency_includes_open_items(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    captured_prompt = {}

    async def fake_llm(system: str, prompt: str) -> dict[str, Any]:
        captured_prompt["text"] = prompt
        return {"sufficient": False}

    with patch.object(loop, "_call_experience_llm", side_effect=fake_llm):
        result = await loop._check_sufficiency(
            "Find all auth handlers",
            ["T1 search(auth) → ok"] * 8,
            last_state_text="[Conclusions] partial\n[Unexplored branches — prioritize these next] Check middleware folder",
        )
    assert result is False
    assert "Check middleware folder" in captured_prompt["text"]
    assert "Open items" in captured_prompt["text"]


@pytest.mark.asyncio
async def test_sufficiency_includes_state_conclusions_and_evidence(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    captured_prompt = {}

    async def fake_llm(system: str, prompt: str) -> dict[str, Any]:
        captured_prompt["text"] = prompt
        return {"sufficient": False}

    state_text = (
        "[Conclusions] Verified handlers loaded\n"
        "[Evidence] T1 read(config), T2 search(auth)\n"
        "[Unexplored branches — prioritize these next] Validate fallback path"
    )

    with patch.object(loop, "_call_experience_llm", side_effect=fake_llm):
        result = await loop._check_sufficiency(
            "Find all auth handlers",
            ["T1 search(auth) → ok"] * 8,
            last_state_text=state_text,
        )
    assert result is False
    assert "State conclusions" in captured_prompt["text"]
    assert "State evidence" in captured_prompt["text"]
    assert "stale" in captured_prompt["text"].lower()


@pytest.mark.asyncio
async def test_sufficiency_string_false_not_truthy(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)

    async def fake_llm(system: str, prompt: str) -> dict[str, Any]:
        del system, prompt
        return {"sufficient": "false"}

    with patch.object(loop, "_call_experience_llm", side_effect=fake_llm):
        result = await loop._check_sufficiency("task", ["T1 exec(x) → ok"] * 8, None)
    assert result is False


@pytest.mark.asyncio
async def test_sufficiency_string_true_parsed(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)

    async def fake_llm(system: str, prompt: str) -> dict[str, Any]:
        del system, prompt
        return {"sufficient": "true"}

    with patch.object(loop, "_call_experience_llm", side_effect=fake_llm):
        result = await loop._check_sufficiency("task", ["T1 exec(x) → ok"] * 8, None)
    assert result is True
