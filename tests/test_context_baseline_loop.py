from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from tests._context_baseline_testkit import (
    BurstToolProvider,
    EmptyFinalAfterSufficientProvider,
    ExitCodeTailProvider,
    HardStopProvider,
    ManyStepsProvider,
    ScriptedProvider,
    fake_tool_success,
    install_web_tool_stub,
    make_loop,
)


def test_context_bytes_est_increases_with_tool_calls(tmp_path: Path, monkeypatch: Any) -> None:
    install_web_tool_stub(monkeypatch)
    provider = ScriptedProvider(tool_rounds=8)
    loop = make_loop(tmp_path, provider, 20)
    loop._experience_mode = "auto"
    loop.tools.execute = fake_tool_success

    final_content, tools_used, tool_trace, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "You are a deterministic test agent."},
                {"role": "user", "content": "Run tools and then finish."},
            ]
        )
    )
    assert final_content == "done"
    assert len(tools_used) >= 6
    assert len(tool_trace) >= 1
    context_sizes = provider.context_bytes_est
    assert len(context_sizes) >= 2
    assert context_sizes[1] > context_sizes[0]


def test_sufficiency_not_skipped_when_tool_steps_jump(tmp_path: Path, monkeypatch: Any) -> None:
    install_web_tool_stub(monkeypatch)
    provider = BurstToolProvider(rounds=3, calls_per_round=3)
    loop = make_loop(tmp_path, provider, 20)
    loop._experience_mode = "auto"
    loop.tools.execute = fake_tool_success
    final_content, tools_used, _, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "You are a deterministic test agent."},
                {"role": "user", "content": "Run tools and then finish."},
            ]
        )
    )
    assert final_content == "done"
    assert len(tools_used) >= 6


def test_exec_error_detected_from_raw_result_when_budget_clips(tmp_path: Path, monkeypatch: Any) -> None:
    install_web_tool_stub(monkeypatch)
    provider = ExitCodeTailProvider()
    loop = make_loop(tmp_path, provider, 6)
    loop._tool_hard_chars = 40
    _, _, tool_trace, total_errors, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "You are a deterministic test agent."},
                {"role": "user", "content": "Run one failing tool then finish."},
            ]
        )
    )
    assert total_errors >= 1
    assert tool_trace and "ERROR" in tool_trace[0]


def test_sufficiency_true_disables_tools_for_final_turn(tmp_path: Path, monkeypatch: Any) -> None:
    install_web_tool_stub(monkeypatch)
    provider = HardStopProvider()
    loop = make_loop(tmp_path, provider, 20)
    loop._experience_mode = "auto"
    loop.tools.execute = fake_tool_success
    final_content, _, _, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "You are a deterministic test agent."},
                {"role": "user", "content": "Run tools and then finish."},
            ]
        )
    )
    assert final_content == "done"
    assert provider.final_tools in (None, [])


def test_sufficiency_uses_trace_window_across_reset(tmp_path: Path, monkeypatch: Any) -> None:
    install_web_tool_stub(monkeypatch)
    provider = ManyStepsProvider(rounds=9)
    loop = make_loop(tmp_path, provider, 20)
    loop.tools.execute = fake_tool_success
    captured_lengths: list[int] = []

    async def fake_check(user_request: str, trace: list[str], last_state_text: str | None = None) -> bool:
        del user_request, last_state_text
        captured_lengths.append(len(trace))
        return False

    setattr(loop, "_check_sufficiency", fake_check)
    asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "You are a deterministic test agent."},
                {"role": "user", "content": "Run tools and then finish."},
            ]
        )
    )
    assert captured_lengths and captured_lengths[0] >= 8


def test_final_empty_response_allows_one_tool_backoff(tmp_path: Path, monkeypatch: Any) -> None:
    install_web_tool_stub(monkeypatch)
    provider = EmptyFinalAfterSufficientProvider()
    loop = make_loop(tmp_path, provider, 20)
    loop._experience_mode = "auto"
    loop.tools.execute = fake_tool_success
    final_content, _, _, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "You are a deterministic test agent."},
                {"role": "user", "content": "Run tools and then finish."},
            ]
        )
    )
    assert final_content in (None, "done")
    assert provider.empty_final_sent is True
