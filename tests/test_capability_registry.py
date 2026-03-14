from __future__ import annotations

from bao.agent.capability_registry import (
    build_available_tool_lines,
    build_capability_registry_snapshot,
)
from bao.agent.tool_catalog import ToolCatalog
from bao.agent.tools.base import Tool
from bao.agent.tools.registry import ToolMetadata, ToolRegistry


def test_capability_registry_snapshot_filters_and_preserves_selection() -> None:
    catalog = ToolCatalog()
    config_data = {
        "tools": {
            "desktop": {"enabled": False},
            "mcpServers": {"figma": {"command": "uvx"}, "broken": {}},
        }
    }
    probes = {
        "figma": {
            "serverName": "figma",
            "canConnect": True,
            "toolNames": ["get_file"],
            "error": "",
        }
    }

    snapshot = build_capability_registry_snapshot(
        catalog=catalog,
        config_data=config_data,
        probe_results=probes,
        query="figma",
        source_filter="mcp",
        selected_id="mcp:figma",
    )

    assert [item["id"] for item in snapshot.items] == ["mcp:figma"]
    assert snapshot.selected_id == "mcp:figma"
    assert snapshot.selected_item["id"] == "mcp:figma"
    assert snapshot.overview["mcpServerCount"] == 2


def test_capability_registry_snapshot_falls_back_to_first_item_when_selection_missing() -> None:
    catalog = ToolCatalog()

    snapshot = build_capability_registry_snapshot(
        catalog=catalog,
        config_data={"tools": {"mcpServers": {}}},
        probe_results={},
        query="",
        source_filter="builtin",
        selected_id="missing:item",
    )

    assert snapshot.items
    assert snapshot.selected_id == snapshot.items[0]["id"]
    assert snapshot.selected_item["id"] == snapshot.items[0]["id"]


def test_build_available_tool_lines_uses_registry_metadata_and_overflow() -> None:
    class DemoTool(Tool):
        @property
        def name(self) -> str:
            return "demo"

        @property
        def description(self) -> str:
            return "demo tool"

        @property
        def parameters(self) -> dict[str, object]:
            return {"type": "object", "properties": {}}

        async def execute(self, **kwargs):  # type: ignore[override]
            return "ok"

    registry = ToolRegistry()
    registry.register(
        DemoTool(),
        metadata=ToolMetadata(short_hint="Do demo work", summary="demo"),
    )
    lines = build_available_tool_lines(
        registry=registry,
        selected_tool_names=["demo", "missing"],
        max_lines=1,
    )

    assert lines == ["- demo: Do demo work", "- plus 1 more tools already exposed this turn"]
