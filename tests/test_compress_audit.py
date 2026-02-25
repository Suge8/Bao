"""Tests for _compress_state audit field (conditional self-audit)."""

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse


class DummyProvider(LLMProvider):
    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> LLMResponse:
        return LLMResponse(content="done", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy"



def _make_loop(tmp_path: Path) -> "AgentLoop":
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
    with patch.object(loop, "_call_experience_llm", new_callable=AsyncMock, return_value=mock_result):
        result = await loop._compress_state(
            tool_trace=["read(f1) → ok", "exec(cmd) → ERROR", "exec(cmd2) → ERROR"],
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
    async def fake_llm(system: str, prompt: str) -> dict:
        captured_prompt["text"] = prompt
        return mock_result
    with patch.object(loop, "_call_experience_llm", side_effect=fake_llm):
        result = await loop._compress_state(
            tool_trace=["read(f1) \u2192 ok"],
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
    async def fake_llm(system: str, prompt: str) -> dict:
        captured_prompt["text"] = prompt
        return {"conclusions": "x", "evidence": "y", "unexplored": "z", "audit": "w"}
    with patch.object(loop, "_call_experience_llm", side_effect=fake_llm):
        await loop._compress_state(
            tool_trace=["a → ok", "b → ERROR", "c → ERROR"],
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
        tool_trace=["a → ok", "b → ERROR"],
        reasoning_snippets=[],
        failed_directions=["b(x)", "c(y)"],
    )
    assert result is not None
    assert "[Audit" not in result
    assert "[Progress]" in result