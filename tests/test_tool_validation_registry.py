from __future__ import annotations

from tests._tool_validation_testkit import (
    CastTestTool,
    CountingSchemaTool,
    SampleTool,
    ToolExecutionResult,
    ToolRegistry,
    tool_result_excerpt,
)


async def test_registry_returns_validation_error() -> None:
    registry = ToolRegistry()
    registry.register(SampleTool())
    result = await registry.execute("sample", {"query": "hi"})
    assert isinstance(result, ToolExecutionResult)
    assert result.code == "invalid_params"
    assert "Invalid parameters" in tool_result_excerpt(result)


async def test_registry_unknown_tool_shows_available() -> None:
    registry = ToolRegistry()
    registry.register(SampleTool())
    result = await registry.execute("nonexistent_tool", {})
    text = tool_result_excerpt(result)
    assert isinstance(result, ToolExecutionResult)
    assert result.code == "tool_not_found"
    assert "Available" in text and "sample" in text and "[Analyze the error" in text


async def test_registry_returns_invalid_params_on_argument_parse_error() -> None:
    registry = ToolRegistry()
    registry.register(SampleTool())
    result = await registry.execute("sample", {}, raw_arguments='{"query"', argument_parse_error="unexpected end of input")
    text = tool_result_excerpt(result)
    assert isinstance(result, ToolExecutionResult)
    assert result.code == "invalid_params"
    assert "failed to parse tool arguments" in text and 'Raw arguments: {"query"' in text


def test_cast_params_string_scalars_and_nested_values() -> None:
    tool = CastTestTool(
        {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "rate": {"type": "number"},
                "enabled": {"type": "boolean"},
                "meta": {"type": "object", "properties": {"port": {"type": "integer"}, "flags": {"type": "array", "items": {"type": "boolean"}}}},
            },
        }
    )
    result = tool.cast_params({"count": "42", "rate": "3.14", "enabled": "false", "meta": {"port": "8080", "flags": ["true", "0"]}})
    assert result["count"] == 42 and result["rate"] == 3.14 and result["enabled"] is False
    assert result["meta"]["port"] == 8080 and result["meta"]["flags"] == [True, False]


def test_cast_params_does_not_apply_unsafe_conversions() -> None:
    tool = CastTestTool({"type": "object", "properties": {"count": {"type": "integer"}, "items": {"type": "array"}, "config": {"type": "object"}, "flag": {"type": "boolean"}}})
    result = tool.cast_params({"count": True, "items": "hello", "config": "", "flag": "maybe"})
    assert result == {"count": True, "items": "hello", "config": "", "flag": "maybe"}
    joined = "; ".join(tool.validate_params(result))
    assert "count should be integer" in joined and "items should be array" in joined
    assert "config should be object" in joined and "flag should be boolean" in joined


async def test_registry_auto_casts_before_validation() -> None:
    registry = ToolRegistry()
    registry.register(CastTestTool({"type": "object", "properties": {"count": {"type": "integer"}, "enabled": {"type": "boolean"}}, "required": ["count", "enabled"]}))
    text = tool_result_excerpt(await registry.execute("cast_test", {"count": "7", "enabled": "true"}))
    assert "'count': 7" in text and "'enabled': True" in text


def test_tool_to_schema_slim_and_registry_cache() -> None:
    tool = CountingSchemaTool()
    full = tool.to_schema()
    slim = tool.to_schema(slim=True)
    assert full["function"]["parameters"]["title"] == "SampleTitle"
    params = slim["function"]["parameters"]
    assert "title" not in params and "description" not in params["properties"]["query"]
    assert params["properties"]["meta"]["required"] == ["tag"]

    registry = ToolRegistry()
    registry.register(tool)
    first_full = registry.get_definitions()
    second_full = registry.get_definitions()
    first_slim = registry.get_definitions(slim=True)
    second_slim = registry.get_definitions(slim=True)
    assert tool.calls == [False, True, False, True]
    assert first_full == second_full and first_slim == second_slim


def test_registry_switches_to_slim_schema_when_tool_count_exceeds_budget() -> None:
    class NamedCountingSchemaTool(CountingSchemaTool):
        def __init__(self, suffix: int) -> None:
            super().__init__()
            self._suffix = suffix

        @property
        def name(self) -> str:
            return f"counting_{self._suffix}"

    registry = ToolRegistry()
    for index in range(9):
        registry.register(NamedCountingSchemaTool(index))
    definitions, slim = registry.get_budgeted_definitions()
    assert slim is True and len(definitions) == 9
    assert "title" not in definitions[0]["function"]["parameters"]
