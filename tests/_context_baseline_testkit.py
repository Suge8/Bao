from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any

from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse, ToolCallRequest

pytest = importlib.import_module("pytest")


def install_web_tool_stub(monkeypatch: Any) -> None:
    module = types.ModuleType("bao.agent.tools.web")

    class _BaseWebTool:
        def __init__(self) -> None:
            self.brave_key = None
            self.tavily_key = None
            self.exa_key = None

        @property
        def description(self) -> str:
            return f"stub {self.name.replace('_', ' ')}"

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

    class WebSearchTool(_BaseWebTool):
        def __init__(self, search_config: Any | None = None, proxy: str | None = None):
            del search_config, proxy
            super().__init__()

        @property
        def name(self) -> str:
            return "web_search"

        @property
        def parameters(self) -> dict[str, Any]:
            return {"type": "object", "properties": {}, "required": []}

    class WebFetchTool(_BaseWebTool):
        def __init__(self, proxy: str | None = None):
            del proxy
            super().__init__()

        @property
        def name(self) -> str:
            return "web_fetch"

        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            }

        def validate_params(self, params: dict[str, Any]) -> list[str]:
            return [] if "url" in params else ["missing required url"]

    setattr(module, "WebSearchTool", WebSearchTool)
    setattr(module, "WebFetchTool", WebFetchTool)
    monkeypatch.setitem(sys.modules, "bao.agent.tools.web", module)


class _BaseLoopProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(api_key=None, api_base=None)

    def get_default_model(self) -> str:
        return "test-provider"


class ScriptedProvider(_BaseLoopProvider):
    def __init__(self, tool_rounds: int = 8):
        super().__init__()
        self.tool_rounds = tool_rounds
        self.call_index = 0
        self.utility_call_count = 0
        self.context_bytes_est: list[int] = []

    async def chat(self, *args: Any, **kwargs: Any) -> LLMResponse:
        messages = _extract_messages(args, kwargs)
        source = kwargs.get("source")
        if source == "utility":
            self.utility_call_count += 1
            return LLMResponse(content='{"sufficient": false}', finish_reason="stop")
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


class BurstToolProvider(_BaseLoopProvider):
    def __init__(self, rounds: int = 3, calls_per_round: int = 3):
        super().__init__()
        self.rounds = rounds
        self.calls_per_round = calls_per_round
        self.call_index = 0
        self.utility_call_count = 0

    async def chat(self, *args: Any, **kwargs: Any) -> LLMResponse:
        if kwargs.get("source") == "utility":
            self.utility_call_count += 1
            return LLMResponse(content='{"sufficient": false}', finish_reason="stop")
        if self.call_index < self.rounds:
            self.call_index += 1
            tool_calls = [
                ToolCallRequest(
                    id=f"tc-{self.call_index}-{idx}",
                    name="exec",
                    arguments={"command": "python -c \"print('x'*100)\""},
                )
                for idx in range(self.calls_per_round)
            ]
            return LLMResponse(content=f"burst-{self.call_index}", tool_calls=tool_calls)
        return LLMResponse(content="done", finish_reason="stop")


class ExitCodeTailProvider(_BaseLoopProvider):
    def __init__(self):
        super().__init__()
        self.call_index = 0

    async def chat(self, *args: Any, **kwargs: Any) -> LLMResponse:
        del args, kwargs
        if self.call_index == 0:
            self.call_index += 1
            return LLMResponse(
                content="run",
                tool_calls=[
                    ToolCallRequest(
                        id="tc-1",
                        name="exec",
                        arguments={"command": "python -c \"print('x'*5000);import sys;sys.exit(1)\""},
                    )
                ],
                finish_reason="tool_calls",
            )
        return LLMResponse(content="done", finish_reason="stop")


class HardStopProvider(_BaseLoopProvider):
    def __init__(self):
        super().__init__()
        self.call_index = 0
        self.final_tools: list[dict[str, Any]] | None = None

    async def chat(self, *args: Any, **kwargs: Any) -> LLMResponse:
        tools = kwargs.get("tools")
        if kwargs.get("source") == "utility":
            return LLMResponse(content='{"sufficient": true}', finish_reason="stop")
        if self.call_index < 8:
            self.call_index += 1
            return LLMResponse(
                content=f"step-{self.call_index}",
                tool_calls=[
                    ToolCallRequest(
                        id=f"tc-{self.call_index}",
                        name="exec",
                        arguments={"command": 'python -c "print(1)"'},
                    )
                ],
                finish_reason="tool_calls",
            )
        self.final_tools = tools
        return LLMResponse(content="done", finish_reason="stop")


class ManyStepsProvider(_BaseLoopProvider):
    def __init__(self, rounds: int = 9):
        super().__init__()
        self.rounds = rounds
        self.call_index = 0

    async def chat(self, *args: Any, **kwargs: Any) -> LLMResponse:
        del args, kwargs
        if self.call_index < self.rounds:
            self.call_index += 1
            return LLMResponse(
                content=f"step-{self.call_index}",
                tool_calls=[
                    ToolCallRequest(
                        id=f"tc-{self.call_index}",
                        name="exec",
                        arguments={"command": 'python -c "print(1)"'},
                    )
                ],
                finish_reason="tool_calls",
            )
        return LLMResponse(content="done", finish_reason="stop")


class EmptyFinalAfterSufficientProvider(_BaseLoopProvider):
    def __init__(self):
        super().__init__()
        self.call_index = 0
        self.empty_final_sent = False
        self.reenabled_tools_seen = False

    async def chat(self, *args: Any, **kwargs: Any) -> LLMResponse:
        tools = kwargs.get("tools")
        if kwargs.get("source") == "utility":
            return LLMResponse(content='{"sufficient": true}', finish_reason="stop")
        if self.call_index < 8:
            self.call_index += 1
            return LLMResponse(
                content=f"step-{self.call_index}",
                tool_calls=[
                    ToolCallRequest(
                        id=f"tc-{self.call_index}",
                        name="exec",
                        arguments={"command": 'python -c "print(1)"'},
                    )
                ],
                finish_reason="tool_calls",
            )
        if not self.empty_final_sent:
            self.empty_final_sent = True
            return LLMResponse(content="", finish_reason="stop")
        self.reenabled_tools_seen = bool(tools)
        return LLMResponse(content="done", finish_reason="stop")


def make_loop(tmp_path: Path, provider: LLMProvider, max_iterations: int):
    from bao.agent.loop import AgentLoop

    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model=provider.get_default_model(),
        max_iterations=max_iterations,
    )
    return loop


def extract_request_messages(args: tuple[Any, ...], kwargs: dict[str, Any]) -> list[dict[str, Any]]:
    return _extract_messages(args, kwargs)


async def fake_tool_success(name: str, params: dict[str, Any]) -> str:
    del name, params
    return "ok"


def _extract_messages(args: tuple[Any, ...], kwargs: dict[str, Any]) -> list[dict[str, Any]]:
    request = args[0] if args else kwargs.get("request") or kwargs.get("messages")
    messages = getattr(request, "messages", request)
    return messages if isinstance(messages, list) else []
