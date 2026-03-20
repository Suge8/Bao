"""Tests for Layer 1: large tool output offloading."""

import asyncio
from pathlib import Path
from typing import Any

from bao.agent.tool_result import ToolTextResult
from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from tests._web_tool_stub_testkit import install_web_tool_stub


class BigOutputProvider(LLMProvider):
    """Provider that returns one tool call, then stops."""

    def __init__(self):
        super().__init__(api_key=None, api_base=None)
        self.call_index = 0
        self.captured_messages: list[list[dict[str, Any]]] = []

    async def chat(self, request: Any, **kwargs: Any) -> LLMResponse:
        del kwargs
        messages = request.messages if hasattr(request, "messages") else request
        self.captured_messages.append([m.copy() for m in messages])
        if self.call_index == 0:
            self.call_index += 1
            return LLMResponse(
                content="running tool",
                tool_calls=[
                    ToolCallRequest(
                        id="tc-big-1",
                        name="exec",
                        arguments={"command": "echo big"},
                    )
                ],
                finish_reason="tool_calls",
            )
        self.call_index += 1
        return LLMResponse(content="done", finish_reason="stop")

    def get_default_model(self) -> str:
        return "big-output-provider"


BIG_OUTPUT = "x" * 10000  # 10000 chars, exceeds 8000 threshold


def test_auto_mode_offloads_large_output(tmp_path: Path, monkeypatch: Any) -> None:
    install_web_tool_stub(monkeypatch)
    from bao.agent.loop import AgentLoop

    provider = BigOutputProvider()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="big-output-provider",
        max_iterations=5,
    )
    loop._ctx_mgmt = "auto"
    loop._tool_offload_chars = 8000
    loop._tool_preview_chars = 3000

    async def fake_execute(name: str, params: dict[str, Any]) -> str:
        del name, params
        return BIG_OUTPUT

    loop.tools.execute = fake_execute

    final_content, tools_used, tool_trace, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "run big tool"},
            ]
        )
    )

    assert final_content == "done"
    # Check that the tool result in messages was replaced (much shorter than 10000)
    all_msgs = provider.captured_messages
    assert len(all_msgs) >= 2
    second_call_msgs = all_msgs[1]
    tool_msgs = [m for m in second_call_msgs if m.get("role") == "tool"]
    assert len(tool_msgs) >= 1
    tool_content = tool_msgs[0].get("content", "")
    assert len(tool_content) < 8000, f"Expected offloaded content but got {len(tool_content)} chars"
    assert "offloaded" in tool_content or "Full output" in tool_content


def test_agent_loop_defaults_to_auto_without_config(tmp_path: Path, monkeypatch: Any) -> None:
    install_web_tool_stub(monkeypatch)
    from bao.agent.loop import AgentLoop

    loop = AgentLoop(
        bus=MessageBus(),
        provider=BigOutputProvider(),
        workspace=tmp_path,
        model="big-output-provider",
        max_iterations=5,
    )

    assert loop._ctx_mgmt == "auto"
    assert loop.subagents._ctx_mgmt == "auto"


def test_observe_mode_does_not_offload(tmp_path: Path, monkeypatch: Any) -> None:
    install_web_tool_stub(monkeypatch)
    from bao.agent.loop import AgentLoop

    provider = BigOutputProvider()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="big-output-provider",
        max_iterations=5,
    )
    loop._ctx_mgmt = "observe"

    async def fake_execute(name: str, params: dict[str, Any]) -> str:
        del name, params
        return BIG_OUTPUT

    loop.tools.execute = fake_execute

    final_content, _, _, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "run big tool"},
            ]
        )
    )

    assert final_content == "done"
    second_call_msgs = provider.captured_messages[1]
    tool_msgs = [m for m in second_call_msgs if m.get("role") == "tool"]
    tool_content = tool_msgs[0].get("content", "")
    assert len(tool_content) < len(BIG_OUTPUT)
    assert "hard-truncated" in tool_content


def test_auto_mode_offloads_file_backed_read_result_without_removing_source(
    tmp_path: Path, monkeypatch: Any
) -> None:
    install_web_tool_stub(monkeypatch)
    from bao.agent.loop import AgentLoop

    provider = BigOutputProvider()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="big-output-provider",
        max_iterations=5,
    )
    loop._ctx_mgmt = "auto"
    loop._tool_offload_chars = 8000
    loop._tool_preview_chars = 3000

    source = tmp_path / "huge.txt"
    source.write_text(BIG_OUTPUT, encoding="utf-8")

    async def fake_execute(name: str, params: dict[str, Any]) -> ToolTextResult:
        del params
        assert name == "exec"
        return ToolTextResult(path=source, chars=len(BIG_OUTPUT), excerpt="preview", cleanup=False)

    loop.tools.execute = fake_execute

    final_content, _, _, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "run big tool"},
            ]
        )
    )

    assert final_content == "done"
    assert source.exists()
    second_call_msgs = provider.captured_messages[1]
    tool_msgs = [m for m in second_call_msgs if m.get("role") == "tool"]
    tool_content = tool_msgs[0].get("content", "")
    assert "offloaded" in tool_content
