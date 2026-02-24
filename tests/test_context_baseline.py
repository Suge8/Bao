import asyncio
import json
from pathlib import Path
import sys
import types
from typing import Any

import pytest

from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse, ToolCallRequest


def _install_web_tool_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("bao.agent.tools.web")

    class WebSearchTool:
        def __init__(self, search_config: Any | None = None):
            del search_config
            self.brave_key = None
            self.tavily_key = None

        @property
        def name(self) -> str:
            return "web_search"

        @property
        def description(self) -> str:
            return "stub web search"

        @property
        def parameters(self) -> dict[str, Any]:
            return {"type": "object", "properties": {}, "required": []}

        async def execute(self, **kwargs: Any) -> str:
            del kwargs
            return "stub"

        def validate_params(self, params: dict[str, Any]) -> list[str]:
            del params
            return []

        def to_schema(self) -> dict[str, Any]:
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": self.parameters,
                },
            }

    class WebFetchTool:
        @property
        def name(self) -> str:
            return "web_fetch"

        @property
        def description(self) -> str:
            return "stub web fetch"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            }

        async def execute(self, **kwargs: Any) -> str:
            del kwargs
            return "stub"

        def validate_params(self, params: dict[str, Any]) -> list[str]:
            if "url" not in params:
                return ["missing required url"]
            return []

        def to_schema(self) -> dict[str, Any]:
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": self.parameters,
                },
            }

    setattr(module, "WebSearchTool", WebSearchTool)
    setattr(module, "WebFetchTool", WebFetchTool)
    monkeypatch.setitem(sys.modules, "bao.agent.tools.web", module)


class ScriptedProvider(LLMProvider):
    def __init__(self, tool_rounds: int = 8):
        super().__init__(api_key=None, api_base=None)
        self.tool_rounds = tool_rounds
        self.call_index = 0
        self.context_bytes_est: list[int] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> LLMResponse:
        del tools, model, max_tokens, temperature
        bytes_est = len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))
        self.context_bytes_est.append(bytes_est)

        if self.call_index < self.tool_rounds:
            self.call_index += 1
            return LLMResponse(
                content=f"step-{self.call_index}",
                tool_calls=[
                    ToolCallRequest(
                        id=f"tc-{self.call_index}",
                        name="exec",
                        arguments={"command": "python -c \"print('x'*5000)\""},
                    )
                ],
                finish_reason="tool_calls",
            )

        self.call_index += 1
        return LLMResponse(content="done", finish_reason="stop")

    def get_default_model(self) -> str:
        return "scripted-provider"


@pytest.mark.asyncio
def test_context_bytes_est_increases_with_tool_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_web_tool_stub(monkeypatch)
    from bao.agent.loop import AgentLoop

    provider = ScriptedProvider(tool_rounds=8)
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="scripted-provider",
        max_iterations=20,
    )

    final_content, tools_used, tool_trace, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "You are a deterministic test agent."},
                {"role": "user", "content": "Run tools and then finish."},
            ]
        )
    )

    assert final_content == "done"
    assert len(tools_used) >= 8
    assert len(tool_trace) >= 8

    context_sizes = provider.context_bytes_est
    assert len(context_sizes) >= 4
    assert context_sizes[1] > context_sizes[0]
    assert context_sizes[2] > context_sizes[1]
    assert context_sizes[3] > context_sizes[2]
