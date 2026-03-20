# ruff: noqa: F403, F405
from __future__ import annotations

from tests._compress_audit_testkit import *


@pytest.mark.asyncio
async def test_audit_included_when_failures_ge_2(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    mock_result = {
        "conclusions": "Found the config file.",
        "evidence": "Read config.jsonc successfully.",
        "unexplored": "Try alternative parser.",
        "audit": "Avoid reading binary files with text tools; use hex dump instead.",
    }
    with patch.object(
        loop, "_call_experience_llm", new_callable=AsyncMock, return_value=mock_result
    ):
        result = await loop._compress_state(
            tool_trace=["T1 read(f1) → ok", "T2 exec(cmd) → ERROR", "T3 exec(cmd2) → ERROR"],
            reasoning_snippets=["thinking about config"],
            failed_directions=["exec(cmd1)", "exec(cmd2)"],
        )
    assert result is not None
    assert "[Audit" in result
    assert "hex dump" in result


@pytest.mark.asyncio
async def test_no_audit_when_few_failures(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    mock_result = {
        "conclusions": "Found the config file.",
        "evidence": "Read config.jsonc.",
        "unexplored": "Try alternative.",
    }
    captured_prompt = {}

    async def fake_llm(system: str, prompt: str) -> dict[str, Any]:
        captured_prompt["text"] = prompt
        return mock_result

    with patch.object(loop, "_call_experience_llm", side_effect=fake_llm):
        result = await loop._compress_state(
            tool_trace=["T1 read(f1) → ok"],
            reasoning_snippets=[],
            failed_directions=["exec(cmd1)"],
        )
    assert result is not None
    assert "[Audit" not in result
    assert "exactly 3 keys" in captured_prompt["text"]
    assert '"audit"' not in captured_prompt["text"]


@pytest.mark.asyncio
async def test_audit_prompt_requests_4_keys_on_failures(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    captured_prompt = {}

    async def fake_llm(system: str, prompt: str) -> dict[str, Any]:
        captured_prompt["text"] = prompt
        return {"conclusions": "x", "evidence": "y", "unexplored": "z", "audit": "w"}

    with patch.object(loop, "_call_experience_llm", side_effect=fake_llm):
        await loop._compress_state(
            tool_trace=["T1 a → ok", "T2 b → ERROR", "T3 c → ERROR"],
            reasoning_snippets=[],
            failed_directions=["b(x)", "c(y)"],
        )
    assert "exactly 4 keys" in captured_prompt["text"]
    assert '"audit"' in captured_prompt["text"]


@pytest.mark.asyncio
async def test_none_mode_unaffected_by_audit(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    loop._experience_mode = "none"
    result = await loop._compress_state(
        tool_trace=["T1 a → ok", "T2 b → ERROR"],
        reasoning_snippets=[],
        failed_directions=["b(x)", "c(y)"],
    )
    assert result is not None
    assert "[Audit" not in result
    assert "[Progress]" in result


@pytest.mark.asyncio
async def test_experience_utility_mode_falls_back_to_main_provider(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    loop._experience_mode = "utility"
    loop._utility_provider = None
    loop.service_tier = "priority"

    mocked_chat = AsyncMock(return_value=LLMResponse(content='{"ok": true}'))
    with patch.object(loop.provider, "chat", new=mocked_chat):
        result = await loop._call_experience_llm("sys", "prompt")

    assert result == {"ok": True}
    mocked_chat.assert_awaited_once()
    await_args = mocked_chat.await_args
    assert await_args is not None
    request = await_args.args[0]
    assert request.source == "utility"
    assert request.service_tier == "priority"


@pytest.mark.asyncio
async def test_compress_prompt_requests_t_references(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    captured_prompt = {}

    async def fake_llm(system: str, prompt: str) -> dict[str, Any]:
        captured_prompt["text"] = prompt
        return {"conclusions": "x", "evidence": "T1 confirmed X", "unexplored": "Run Y"}

    with patch.object(loop, "_call_experience_llm", side_effect=fake_llm):
        await loop._compress_state(
            tool_trace=["T1 read(f) → ok", "T2 search(q) → ok"],
            reasoning_snippets=[],
            failed_directions=[],
        )
    assert "T#" in captured_prompt["text"]
    assert (
        "imperative" in captured_prompt["text"].lower()
        or "action" in captured_prompt["text"].lower()
    )


@pytest.mark.asyncio
async def test_compress_state_normalizes_multiline_sections(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)

    async def fake_llm(system: str, prompt: str) -> dict[str, Any]:
        del system, prompt
        return {
            "conclusions": "line1\nline2",
            "evidence": "ev1\nev2",
            "unexplored": "step1\nstep2",
            "audit": "fix1\nfix2",
        }

    with patch.object(loop, "_call_experience_llm", side_effect=fake_llm):
        result = await loop._compress_state(
            tool_trace=["T1 read(f) → ok", "T2 exec(x) → ERROR", "T3 exec(y) → ERROR"],
            reasoning_snippets=[],
            failed_directions=["exec(x)", "exec(y)"],
        )

    assert result is not None
    assert "line1 line2" in result
    assert "ev1 ev2" in result
    assert "step1 step2" in result
    assert "fix1 fix2" in result
