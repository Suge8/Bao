from __future__ import annotations

from types import SimpleNamespace

from bao.agent.tools._mcp_wrapper_models import MCPToolWrapperSpec
from bao.agent.tools.mcp import (
    MCPToolWrapper,
    _reached_global_cap,
    _reached_server_cap,
    _resolve_server_max_tools,
    _resolve_server_slim_schema,
    _resolve_transport_type,
    _slim_schema,
)


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
                "properties": {"value": {"type": "integer", "examples": [1, 2], "minimum": 1}},
                "required": ["value"],
            },
        },
        "required": ["mode"],
        "example": {"mode": "fast"},
    }
    slim = _slim_schema(schema, max_description_chars=120)
    assert "title" not in slim and "example" not in slim
    assert "default" not in slim["properties"]["mode"]
    assert "examples" not in slim["properties"]["nested"]["properties"]["value"]
    assert slim["properties"]["nested"]["x-meta"] == {"internal": True}
    assert slim["required"] == ["mode"]
    assert len(slim["description"]) <= 123
    assert len(slim["properties"]["mode"]["description"]) <= 123


def test_mcp_wrapper_can_disable_slim_schema() -> None:
    tool_def = SimpleNamespace(
        name="demo",
        description="x" * 210,
        inputSchema={"type": "object", "properties": {"q": {"type": "string", "default": "abc", "description": "y" * 210}}, "required": ["q"]},
    )
    slim_wrapper = MCPToolWrapper(
        object(),
        MCPToolWrapperSpec(server_name="svc", tool_def=tool_def, slim_schema=True),
    )
    raw_wrapper = MCPToolWrapper(
        object(),
        MCPToolWrapperSpec(server_name="svc", tool_def=tool_def, slim_schema=False),
    )
    assert "default" not in slim_wrapper.parameters["properties"]["q"]
    assert len(slim_wrapper.description) < len(raw_wrapper.description)
    assert raw_wrapper.parameters["properties"]["q"]["default"] == "abc"


def test_server_override_and_cap_helpers() -> None:
    assert _resolve_server_slim_schema(SimpleNamespace(), True) is True
    assert _resolve_server_slim_schema(SimpleNamespace(slim_schema=False), True) is False
    assert _resolve_server_slim_schema(SimpleNamespace(slim_schema=True), False) is True
    assert _resolve_server_slim_schema(SimpleNamespace(slim_schema="false"), True) is True
    assert _resolve_server_max_tools(SimpleNamespace()) is None
    assert _resolve_server_max_tools(SimpleNamespace(max_tools=8)) == 8
    assert _resolve_server_max_tools(SimpleNamespace(max_tools=0)) == 0
    assert _resolve_server_max_tools(SimpleNamespace(max_tools=-3)) == 0
    assert _resolve_server_max_tools(SimpleNamespace(max_tools=True)) is None
    assert _resolve_server_max_tools(SimpleNamespace(max_tools="8")) is None
    assert _reached_global_cap(total_registered=4, pending_count=1, max_tools=5) is True
    assert _reached_server_cap(server_count=1, pending_count=1, server_max_tools=2) is True


def test_resolve_transport_type_rules() -> None:
    assert _resolve_transport_type(SimpleNamespace(type="sse", command="ignored", url="https://example.com/mcp")) == "sse"
    assert _resolve_transport_type(SimpleNamespace(type="", command="npx", url="")) == "stdio"
    assert _resolve_transport_type(SimpleNamespace(type="", command="", url="https://x/y/sse")) == "sse"
    assert _resolve_transport_type(SimpleNamespace(type="", command="", url="https://x/y/mcp")) == "streamableHttp"
    assert _resolve_transport_type(SimpleNamespace(type="", command="", url="")) is None


def test_wrapper_fallbacks_and_x_prefixed_names() -> None:
    assert MCPToolWrapper(object(), MCPToolWrapperSpec(server_name="svc", tool_def=SimpleNamespace(name="bad", description="ok", inputSchema="not-a-dict"), slim_schema=True)).parameters == {"type": "object", "properties": {}}
    assert MCPToolWrapper(object(), MCPToolWrapperSpec(server_name="svc", tool_def=SimpleNamespace(name="bad", description="ok", inputSchema=None), slim_schema=False)).parameters == {"type": "object", "properties": {}}
    assert MCPToolWrapper(object(), MCPToolWrapperSpec(server_name="svc", tool_def=SimpleNamespace(name="mytool", description=None, inputSchema={"type": "object", "properties": {}}), slim_schema=True)).description == "mytool"
    assert MCPToolWrapper(object(), MCPToolWrapperSpec(server_name="svc", tool_def=SimpleNamespace(name="mytool", description=42, inputSchema={"type": "object", "properties": {}}), slim_schema=False)).description == "mytool"
    slim = _slim_schema({"type": "object", "properties": {"x-api-key": {"type": "string"}, "normal": {"type": "string"}}, "required": ["x-api-key"]})
    assert "x-api-key" in slim["properties"] and slim["required"] == ["x-api-key"]
