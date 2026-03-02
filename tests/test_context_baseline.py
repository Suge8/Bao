import asyncio
import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any

from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse, ToolCallRequest

pytest = importlib.import_module("pytest")


def _install_web_tool_stub(monkeypatch: Any) -> None:
    module = types.ModuleType("bao.agent.tools.web")

    class WebSearchTool:
        def __init__(self, search_config: Any | None = None, proxy: str | None = None):
            del search_config, proxy
            self.brave_key = None
            self.tavily_key = None
            self.exa_key = None

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
        def __init__(self, proxy: str | None = None):
            del proxy

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
        self.utility_call_count = 0
        self.context_bytes_est: list[int] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        on_progress=None,
        **kwargs: Any,
    ) -> LLMResponse:
        source = kwargs.get("source")
        del tools, model, max_tokens, temperature, on_progress
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

    def get_default_model(self) -> str:
        return "scripted-provider"


class BurstToolProvider(LLMProvider):
    def __init__(self, rounds: int = 3, calls_per_round: int = 3):
        super().__init__(api_key=None, api_base=None)
        self.rounds = rounds
        self.calls_per_round = calls_per_round
        self.call_index = 0
        self.utility_call_count = 0

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        on_progress=None,
        **kwargs: Any,
    ) -> LLMResponse:
        del messages, tools, model, max_tokens, temperature, on_progress
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

    def get_default_model(self) -> str:
        return "burst-provider"


class ExitCodeTailProvider(LLMProvider):
    def __init__(self):
        super().__init__(api_key=None, api_base=None)
        self.call_index = 0

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        on_progress=None,
        **kwargs: Any,
    ) -> LLMResponse:
        del messages, tools, model, max_tokens, temperature, on_progress, kwargs
        if self.call_index == 0:
            self.call_index += 1
            return LLMResponse(
                content="run",
                tool_calls=[
                    ToolCallRequest(
                        id="tc-1",
                        name="exec",
                        arguments={
                            "command": "python -c \"print('x'*5000);import sys;sys.exit(1)\""
                        },
                    )
                ],
                finish_reason="tool_calls",
            )
        return LLMResponse(content="done", finish_reason="stop")

    def get_default_model(self) -> str:
        return "exit-code-tail"


class HardStopProvider(LLMProvider):
    def __init__(self):
        super().__init__(api_key=None, api_base=None)
        self.call_index = 0
        self.final_tools: list[dict[str, Any]] | None = None

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        on_progress=None,
        **kwargs: Any,
    ) -> LLMResponse:
        del messages, model, max_tokens, temperature, on_progress
        source = kwargs.get("source")
        if source == "utility":
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

    def get_default_model(self) -> str:
        return "hard-stop"


class ManyStepsProvider(LLMProvider):
    def __init__(self, rounds: int = 9):
        super().__init__(api_key=None, api_base=None)
        self.rounds = rounds
        self.call_index = 0

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        on_progress=None,
        **kwargs: Any,
    ) -> LLMResponse:
        del messages, tools, model, max_tokens, temperature, on_progress, kwargs
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

    def get_default_model(self) -> str:
        return "many-steps"


def test_context_bytes_est_increases_with_tool_calls(tmp_path: Path, monkeypatch: Any) -> None:
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
    loop._experience_mode = "auto"

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
    # After RE-TRAC reset, tool_trace only contains steps since last compression.
    # tools_used is cumulative and still >= 8; tool_trace resets after every 5-step compression.
    assert len(tool_trace) >= 1  # at least some steps after last reset
    assert provider.utility_call_count >= 1

    context_sizes = provider.context_bytes_est
    assert len(context_sizes) >= 4
    assert context_sizes[1] > context_sizes[0]
    assert context_sizes[2] > context_sizes[1]
    assert context_sizes[3] > context_sizes[2]


def test_sufficiency_not_skipped_when_tool_steps_jump(tmp_path: Path, monkeypatch: Any) -> None:
    _install_web_tool_stub(monkeypatch)
    from bao.agent.loop import AgentLoop

    provider = BurstToolProvider(rounds=3, calls_per_round=3)
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="burst-provider",
        max_iterations=20,
    )
    loop._experience_mode = "auto"

    final_content, tools_used, _, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "You are a deterministic test agent."},
                {"role": "user", "content": "Run tools and then finish."},
            ]
        )
    )

    assert final_content == "done"
    assert len(tools_used) == 9
    assert provider.utility_call_count >= 1


def test_exec_error_detected_from_raw_result_when_budget_clips(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _install_web_tool_stub(monkeypatch)
    from bao.agent.loop import AgentLoop

    provider = ExitCodeTailProvider()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="exit-code-tail",
        max_iterations=6,
    )
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
    assert tool_trace
    assert "ERROR" in tool_trace[0]


def test_sufficiency_true_disables_tools_for_final_turn(tmp_path: Path, monkeypatch: Any) -> None:
    _install_web_tool_stub(monkeypatch)
    from bao.agent.loop import AgentLoop

    provider = HardStopProvider()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="hard-stop",
        max_iterations=20,
    )
    loop._experience_mode = "auto"

    final_content, _, _, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "You are a deterministic test agent."},
                {"role": "user", "content": "Run tools and then finish."},
            ]
        )
    )

    assert final_content == "done"
    assert provider.final_tools == []


def test_sufficiency_uses_trace_window_across_reset(tmp_path: Path, monkeypatch: Any) -> None:
    _install_web_tool_stub(monkeypatch)
    from bao.agent.loop import AgentLoop

    provider = ManyStepsProvider(rounds=9)
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="many-steps",
        max_iterations=20,
    )
    captured_lengths: list[int] = []

    async def fake_check(
        user_request: str, trace: list[str], last_state_text: str | None = None
    ) -> bool:
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

    assert captured_lengths
    assert captured_lengths[0] >= 8


class EmptyFinalAfterSufficientProvider(LLMProvider):
    def __init__(self):
        super().__init__(api_key=None, api_base=None)
        self.call_index = 0
        self.empty_final_sent = False
        self.reenabled_tools_seen = False

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        on_progress=None,
        **kwargs: Any,
    ) -> LLMResponse:
        del messages, model, max_tokens, temperature, on_progress
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

    def get_default_model(self) -> str:
        return "empty-final"


def test_final_empty_response_allows_one_tool_backoff(tmp_path: Path, monkeypatch: Any) -> None:
    _install_web_tool_stub(monkeypatch)
    from bao.agent.loop import AgentLoop

    provider = EmptyFinalAfterSufficientProvider()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="empty-final",
        max_iterations=20,
    )
    loop._experience_mode = "auto"

    final_content, _, _, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "You are a deterministic test agent."},
                {"role": "user", "content": "Run tools and then finish."},
            ]
        )
    )

    assert final_content == "done"
    assert provider.reenabled_tools_seen is True
