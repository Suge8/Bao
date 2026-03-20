from __future__ import annotations

from pathlib import Path
from typing import Any

from bao.providers.base import LLMResponse
from tests._tool_observability_testkit import (
    LoopSpec,
    PlannedProvider,
    ToolObservabilityProvider,
    build_loop,
    run_default_turn,
    tool_call_response,
)


def test_run_agent_loop_collects_tool_observability(tmp_path: Path) -> None:
    loop = build_loop(tmp_path, LoopSpec(provider=ToolObservabilityProvider(with_tool_calls=True), max_iterations=4))
    loop._tool_exposure_mode = "off"

    final_content, tools_used, _, _, _ = run_default_turn(loop, "call tools")

    assert final_content == "done"
    assert tools_used == ["missing_tool", "read_file"]

    obs = loop._last_tool_observability
    assert obs["schema_samples"] >= 1
    assert obs["schema_tool_count_last"] > 0
    assert obs["schema_bytes_last"] > 0
    assert obs["tool_calls_total"] == 2
    assert obs["tool_calls_error"] == 2
    assert obs["invalid_parameter_errors"] == 1
    assert obs["tool_not_found_errors"] == 1
    assert obs["retry_rate_proxy"] == 0.5
    assert "retry_attempts_proxy" not in obs
    assert "post_error_tool_calls_proxy" not in obs
    assert "tool_selection_hit_rate" not in obs
    assert "parameter_fill_success_rate" not in obs

def test_interrupted_tool_call_not_counted_as_ok(tmp_path: Path) -> None:
    provider = PlannedProvider(
        [
            tool_call_response("read_file", {"path": "x"}),
            LLMResponse(content="done", finish_reason="stop"),
        ]
    )
    loop = build_loop(tmp_path, LoopSpec(provider=provider, max_iterations=3))
    loop._tool_exposure_mode = "off"

    async def _fake_execute(name: str, params: dict[str, Any], **kwargs: Any) -> str:
        del name, params, kwargs
        return "Cancelled by soft interrupt."

    loop.tools.execute = _fake_execute
    final_content, _, _, _, _ = run_default_turn(loop, "call tools")

    assert final_content == "done"
    obs = loop._last_tool_observability
    assert obs["tool_calls_total"] == 1
    assert obs["interrupted_tool_calls"] == 1
    assert obs["tool_calls_error"] == 0
    assert obs["tool_calls_ok"] == 0


def test_run_agent_loop_blocks_tool_not_exposed_for_turn(tmp_path: Path) -> None:
    provider = PlannedProvider(
        [
            tool_call_response("web_fetch", {"url": "https://example.com"}),
            LLMResponse(content="done", finish_reason="stop"),
        ]
    )
    loop = build_loop(tmp_path, LoopSpec(provider=provider, max_iterations=3))
    loop._tool_exposure_mode = "auto"
    loop._tool_exposure_domains = {"core"}

    executed: list[str] = []

    async def _fake_execute(name: str, params: dict[str, Any]) -> str:
        executed.append(name)
        del params
        return "ok"

    loop.tools.execute = _fake_execute
    final_content, _, _, _, _ = run_default_turn(loop, "你好")

    assert final_content == "done"
    assert executed == []
    assert loop._last_tool_observability["tool_not_found_errors"] == 1
