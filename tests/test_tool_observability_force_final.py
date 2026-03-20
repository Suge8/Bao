from __future__ import annotations

from pathlib import Path
from typing import Any

from bao.agent._loop_tool_runtime_models import LoopPreIterationRequest
from bao.providers.base import LLMResponse
from tests._tool_observability_testkit import (
    LoopSpec,
    PlannedProvider,
    build_loop,
    run_default_turn,
    tool_call_response,
)


def test_run_agent_loop_force_final_never_executes_tool_calls(tmp_path: Path) -> None:
    provider = PlannedProvider(
        [
            tool_call_response("exec", {"command": "echo x"}),
            LLMResponse(content="done", finish_reason="stop"),
        ],
        capture_tools=True,
    )
    loop = build_loop(tmp_path, LoopSpec(provider=provider, max_iterations=3))

    executed: list[str] = []

    async def _fake_execute(name: str, params: dict[str, Any]) -> str:
        executed.append(name)
        del params
        return "ok"

    async def _force_final_precheck(request: LoopPreIterationRequest):
        state = request.state
        state.force_final_response = True
        return request.messages

    loop.tools.execute = _fake_execute
    loop._apply_pre_iteration_checks = _force_final_precheck

    final_content, _, _, _, _ = run_default_turn(loop, "call tools")

    assert final_content == "done"
    assert executed == []
    assert provider.captured_tools
    assert provider.captured_tools[0] in (None, [])
