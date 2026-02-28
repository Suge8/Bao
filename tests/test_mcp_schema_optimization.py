from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from bao.agent.loop import AgentLoop
from bao.agent.tools.mcp import MCPToolWrapper, _slim_schema
from bao.bus.queue import MessageBus
from bao.config.schema import Config
from bao.providers.base import LLMProvider, LLMResponse


class DummyProvider(LLMProvider):
    def __init__(self):
        super().__init__(api_key=None, api_base=None)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        on_progress=None,
        **kwargs: Any,
    ) -> LLMResponse:
        del messages, tools, model, max_tokens, temperature, on_progress, kwargs
        return LLMResponse(content="ok", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy/model"


def test_slim_schema_keeps_constraints_and_removes_metadata() -> None:
    schema = {
        "type": "object",
        "title": "Verbose Tool",
        "description": "a" * 220,
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["fast", "slow"],
                "default": "fast",
                "description": "b" * 220,
            },
            "nested": {
                "type": "object",
                "x-meta": {"internal": True},
                "properties": {
                    "value": {
                        "type": "integer",
                        "examples": [1, 2],
                        "minimum": 1,
                    }
                },
                "required": ["value"],
            },
        },
        "required": ["mode"],
        "example": {"mode": "fast"},
    }

    slim = _slim_schema(schema, max_description_chars=120)

    assert "title" not in slim
    assert "example" not in slim
    assert "default" not in slim["properties"]["mode"]
    assert "examples" not in slim["properties"]["nested"]["properties"]["value"]
    assert slim["properties"]["nested"]["x-meta"] == {"internal": True}

    assert slim["type"] == "object"
    assert slim["required"] == ["mode"]
    assert slim["properties"]["mode"]["enum"] == ["fast", "slow"]
    assert slim["properties"]["nested"]["required"] == ["value"]
    assert slim["properties"]["nested"]["properties"]["value"]["minimum"] == 1

    assert len(slim["description"]) <= 123
    assert len(slim["properties"]["mode"]["description"]) <= 123


def test_mcp_wrapper_can_disable_slim_schema() -> None:
    tool_def = SimpleNamespace(
        name="demo",
        description="x" * 210,
        inputSchema={
            "type": "object",
            "properties": {
                "q": {
                    "type": "string",
                    "default": "abc",
                    "description": "y" * 210,
                }
            },
            "required": ["q"],
        },
    )

    slim_wrapper = MCPToolWrapper(object(), "svc", tool_def, slim_schema=True)
    raw_wrapper = MCPToolWrapper(object(), "svc", tool_def, slim_schema=False)

    assert "default" not in slim_wrapper.parameters["properties"]["q"]
    assert len(slim_wrapper.description) < len(raw_wrapper.description)
    assert raw_wrapper.parameters["properties"]["q"]["default"] == "abc"


async def test_agentloop_passes_mcp_slim_and_max_tools(monkeypatch: Any, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    async def fake_connect(
        mcp_servers: dict[str, Any],
        registry,
        stack,
        max_tools: int = 50,
        slim_schema: bool = True,
    ) -> tuple[int, int]:
        del registry, stack
        captured["mcp_servers"] = mcp_servers
        captured["max_tools"] = max_tools
        captured["slim_schema"] = slim_schema
        return 1, 1

    monkeypatch.setattr("bao.agent.tools.mcp.connect_mcp_servers", fake_connect)

    config = Config()
    config.tools.mcp_max_tools = 7
    config.tools.mcp_slim_schema = False

    loop = AgentLoop(
        bus=MessageBus(),
        provider=DummyProvider(),
        workspace=tmp_path,
        mcp_servers={"demo": SimpleNamespace(command="demo")},
        config=config,
    )

    await loop._connect_mcp()

    assert captured["mcp_servers"]
    assert captured["max_tools"] == 7
    assert captured["slim_schema"] is False

    if loop._mcp_stack:
        await loop._mcp_stack.aclose()


def test_mcp_wrapper_non_dict_input_schema() -> None:
    """Non-dict inputSchema should fallback to empty object schema."""
    tool_def = SimpleNamespace(name="bad", description="ok", inputSchema="not-a-dict")
    wrapper = MCPToolWrapper(object(), "svc", tool_def, slim_schema=True)
    assert wrapper.parameters == {"type": "object", "properties": {}}


def test_mcp_wrapper_none_input_schema() -> None:
    """None inputSchema should fallback to empty object schema."""
    tool_def = SimpleNamespace(name="bad", description="ok", inputSchema=None)
    wrapper = MCPToolWrapper(object(), "svc", tool_def, slim_schema=False)
    assert wrapper.parameters == {"type": "object", "properties": {}}


def test_mcp_wrapper_non_string_description() -> None:
    """Non-string description should fallback to tool name."""
    tool_def = SimpleNamespace(
        name="mytool", description=None, inputSchema={"type": "object", "properties": {}}
    )
    wrapper = MCPToolWrapper(object(), "svc", tool_def, slim_schema=True)
    assert wrapper.description == "mytool"


def test_mcp_wrapper_int_description() -> None:
    """Integer description should fallback to tool name."""
    tool_def = SimpleNamespace(
        name="mytool", description=42, inputSchema={"type": "object", "properties": {}}
    )
    wrapper = MCPToolWrapper(object(), "svc", tool_def, slim_schema=False)
    assert wrapper.description == "mytool"


def test_agentloop_bool_mcp_max_tools_ignored(tmp_path: Path) -> None:
    """bool value for mcp_max_tools should be ignored, fallback to 50."""
    config = Config()
    config.tools.mcp_max_tools = True  # type: ignore[assignment]
    loop = AgentLoop(
        bus=MessageBus(),
        provider=DummyProvider(),
        workspace=tmp_path,
        mcp_servers={},
        config=config,
    )
    assert loop._mcp_max_tools == 50


def test_agentloop_negative_mcp_max_tools_clamped_to_zero(tmp_path: Path) -> None:
    config = Config()
    config.tools.mcp_max_tools = -3
    loop = AgentLoop(
        bus=MessageBus(),
        provider=DummyProvider(),
        workspace=tmp_path,
        mcp_servers={},
        config=config,
    )
    assert loop._mcp_max_tools == 0


def test_slim_schema_keeps_x_prefixed_parameter_names() -> None:
    schema = {
        "type": "object",
        "properties": {
            "x-api-key": {"type": "string", "description": "key"},
            "normal": {"type": "string"},
        },
        "required": ["x-api-key"],
    }
    slim = _slim_schema(schema)
    assert "x-api-key" in slim["properties"]
    assert slim["required"] == ["x-api-key"]


async def test_mcp_connected_false_when_all_fail(monkeypatch: Any, tmp_path: Path) -> None:
    """_mcp_connected should be False when connect_mcp_servers returns 0."""

    async def fake_connect_zero(*args, **kwargs) -> tuple[int, int]:
        return 0, 0

    monkeypatch.setattr("bao.agent.tools.mcp.connect_mcp_servers", fake_connect_zero)
    config = Config()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=DummyProvider(),
        workspace=tmp_path,
        mcp_servers={"demo": SimpleNamespace(command="demo")},
        config=config,
    )
    await loop._connect_mcp()
    assert loop._mcp_connected is False
    assert loop._mcp_connect_succeeded is False
    if loop._mcp_stack:
        await loop._mcp_stack.aclose()


async def test_mcp_connected_true_when_some_succeed(monkeypatch: Any, tmp_path: Path) -> None:
    """_mcp_connected should be True when connect_mcp_servers returns > 0."""

    async def fake_connect_ok(*args, **kwargs) -> tuple[int, int]:
        return 2, 1

    monkeypatch.setattr("bao.agent.tools.mcp.connect_mcp_servers", fake_connect_ok)
    config = Config()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=DummyProvider(),
        workspace=tmp_path,
        mcp_servers={"demo": SimpleNamespace(command="demo")},
        config=config,
    )
    await loop._connect_mcp()
    assert loop._mcp_connected is True
    assert loop._mcp_connect_succeeded is True
    if loop._mcp_stack:
        await loop._mcp_stack.aclose()


async def test_mcp_no_tools_retries_on_next_connect_attempt(
    monkeypatch: Any, tmp_path: Path
) -> None:
    calls = {"count": 0}

    async def fake_connect_no_tools(*args, **kwargs) -> tuple[int, int]:
        calls["count"] += 1
        return 0, 1

    monkeypatch.setattr("bao.agent.tools.mcp.connect_mcp_servers", fake_connect_no_tools)
    config = Config()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=DummyProvider(),
        workspace=tmp_path,
        mcp_servers={"demo": SimpleNamespace(command="demo")},
        config=config,
    )
    await loop._connect_mcp()
    await loop._connect_mcp()

    assert calls["count"] == 2
    assert loop._mcp_connected is False
    assert loop._mcp_connect_succeeded is True
    assert loop._mcp_stack is None
