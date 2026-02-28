"""Tests for trajectory compression: audit, T# trace, validation, sufficiency."""

import importlib
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse

pytest = importlib.import_module("pytest")


class DummyProvider(LLMProvider):
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        on_progress: Any = None,
        **kwargs: Any,
    ) -> LLMResponse:
        del messages, tools, model, max_tokens, temperature, on_progress, kwargs
        return LLMResponse(content="done", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy"


def _make_loop(tmp_path: Path) -> Any:
    from bao.agent.loop import AgentLoop

    loop = AgentLoop(
        bus=MessageBus(),
        provider=DummyProvider(),
        workspace=tmp_path,
        model="dummy",
    )
    loop._experience_mode = "auto"
    return loop


# ---------------------------------------------------------------------------
# Audit trigger condition: only when failed_directions >= 2
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_included_when_failures_ge_2(tmp_path: Path) -> None:
    """When failed_directions has >= 2 items, audit field appears in output."""
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
    """When failed_directions has < 2 items, prompt asks for 3 keys (no audit)."""
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
            failed_directions=["exec(cmd1)"],  # only 1 failure
        )
    assert result is not None
    assert "[Audit" not in result
    # Prompt should say "3 keys" not "4 keys"
    assert "exactly 3 keys" in captured_prompt["text"]
    assert '"audit"' not in captured_prompt["text"]


@pytest.mark.asyncio
async def test_audit_prompt_requests_4_keys_on_failures(tmp_path: Path) -> None:
    """When >= 2 failures, prompt explicitly asks for 4 keys including audit."""
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
    """experience_mode='none' uses static fallback, no LLM call, no audit."""
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

    mocked_chat = AsyncMock(return_value=LLMResponse(content='{"ok": true}'))
    with patch.object(loop.provider, "chat", new=mocked_chat):
        result = await loop._call_experience_llm("sys", "prompt")

    assert result == {"ok": True}
    mocked_chat.assert_awaited_once()
    await_args = mocked_chat.await_args
    assert await_args is not None
    assert await_args.kwargs["source"] == "utility"


# ---------------------------------------------------------------------------
# _validate_state: rule-based fallback for missing fields
# ---------------------------------------------------------------------------


def test_validate_state_fills_missing_conclusions() -> None:
    """_validate_state fills conclusions when LLM omits it."""
    from bao.agent.shared import _validate_state

    result = {"evidence": "some evidence", "unexplored": "try X"}
    trace = ["T1 read(f) \u2192 ok", "T2 search(q) \u2192 ok"]
    validated = _validate_state(result, trace, [])
    assert "conclusions" in validated
    assert "2 steps" in validated["conclusions"]


def test_validate_state_fills_missing_evidence() -> None:
    """_validate_state fills evidence from successful trace steps."""
    from bao.agent.shared import _validate_state

    result = {"conclusions": "found it", "unexplored": "try Y"}
    trace = ["T1 read(f) \u2192 ok", "T2 exec(cmd) \u2192 ERROR", "T3 search(q) \u2192 ok"]
    validated = _validate_state(result, trace, ["exec(cmd)"])
    assert "evidence" in validated
    assert "read" in validated["evidence"] or "search" in validated["evidence"]


def test_validate_state_fills_unexplored_from_failures() -> None:
    """_validate_state suggests retry when unexplored is missing and failures exist."""
    from bao.agent.shared import _validate_state

    result = {"conclusions": "partial", "evidence": "T1"}
    validated = _validate_state(result, ["T1 a \u2192 ok"], ["b(x)", "c(y)"])
    assert "unexplored" in validated
    assert "Retry" in validated["unexplored"]


def test_validate_state_fills_unexplored_without_failures() -> None:
    from bao.agent.shared import _validate_state

    result = {"conclusions": "partial", "evidence": "T1"}
    validated = _validate_state(result, ["T1 a → ok"], [])
    assert "unexplored" in validated
    assert "verify remaining requirements" in validated["unexplored"]


# ---------------------------------------------------------------------------
# check_sufficiency: last_state_text integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sufficiency_includes_open_items(tmp_path: Path) -> None:
    """check_sufficiency prompt includes unexplored items from last_state_text."""
    loop = _make_loop(tmp_path)
    captured_prompt = {}

    async def fake_llm(system: str, prompt: str) -> dict[str, Any]:
        captured_prompt["text"] = prompt
        return {"sufficient": False}

    with patch.object(loop, "_call_experience_llm", side_effect=fake_llm):
        result = await loop._check_sufficiency(
            "Find all auth handlers",
            ["T1 search(auth) \u2192 ok"] * 8,
            last_state_text="[Conclusions] partial\n[Unexplored branches \u2014 prioritize these next] Check middleware folder",
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


# ---------------------------------------------------------------------------
# compress_state prompt upgrade: T# references + actionable unexplored
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compress_prompt_requests_t_references(tmp_path: Path) -> None:
    """compress_state prompt instructs LLM to reference T# numbers in evidence."""
    loop = _make_loop(tmp_path)
    captured_prompt = {}

    async def fake_llm(system: str, prompt: str) -> dict[str, Any]:
        captured_prompt["text"] = prompt
        return {"conclusions": "x", "evidence": "T1 confirmed X", "unexplored": "Run Y"}

    with patch.object(loop, "_call_experience_llm", side_effect=fake_llm):
        await loop._compress_state(
            tool_trace=["T1 read(f) \u2192 ok", "T2 search(q) \u2192 ok"],
            reasoning_snippets=[],
            failed_directions=[],
        )
    assert "T#" in captured_prompt["text"]
    assert (
        "imperative" in captured_prompt["text"].lower()
        or "action" in captured_prompt["text"].lower()
    )


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


def test_trace_arg_summary_redacts_write_and_exec() -> None:
    from bao.agent.shared import summarize_tool_args_for_trace

    write_preview = summarize_tool_args_for_trace(
        "write_file",
        {"path": "src/app.py", "content": "secret"},
    )
    exec_preview = summarize_tool_args_for_trace("exec", {"command": "echo secret"})

    assert write_preview == "src/app.py"
    assert exec_preview.startswith("<redacted:")


def test_trace_entry_sanitizes_newlines() -> None:
    from bao.agent.shared import build_tool_trace_entry

    entry = build_tool_trace_entry(1, "exec", "line1\nline2", False, "ok\nnext")
    assert "\n" not in entry
    assert "line1 line2" in entry


def test_push_failed_direction_keeps_recent_window() -> None:
    from bao.agent.shared import push_failed_direction

    failed: list[str] = []
    for i in range(25):
        push_failed_direction(failed, f"f{i}")

    assert len(failed) == 20
    assert failed[0] == "f5"
    assert failed[-1] == "f24"


def test_push_failed_direction_deduplicates_adjacent_entries() -> None:
    from bao.agent.shared import push_failed_direction

    failed: list[str] = []
    push_failed_direction(failed, "exec(a)")
    push_failed_direction(failed, "exec(a)")
    push_failed_direction(failed, "exec(b)")
    assert failed == ["exec(a)", "exec(b)"]


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
