from __future__ import annotations

from bao.agent.capability_registry import (
    CapabilityRegistryRequest,
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
        request=CapabilityRegistryRequest(
            config_data=config_data,
            probe_results=probes,
            query="figma",
            source_filter="mcp",
            selected_id="mcp:figma",
            tool_observability={
                "tool_exposure": {
                    "enabled_domains": [
                        "core",
                        "messaging",
                        "handoff",
                        "web_research",
                        "desktop_automation",
                        "coding_backend",
                    ],
                    "selected_domains": ["core"],
                    "ordered_tool_names": ["get_file"],
                }
            },
        ),
    )

    assert [item["id"] for item in snapshot.items] == ["mcp:figma"]
    assert snapshot.selected_id == "mcp:figma"
    assert snapshot.selected_item["id"] == "mcp:figma"
    assert snapshot.overview["mcpServerCount"] == 2
    assert snapshot.overview["summaryMetrics"]
    assert snapshot.selected_item["exposureState"] == "exposed_last_run"
    assert snapshot.selected_item["displayStatusLabel"] == {"zh": "已连接", "en": "Connected"}
    assert snapshot.selected_item["includesSummaryDisplay"] == {
        "zh": "最近一次探测发现 1 个运行时工具。",
        "en": "The latest probe found 1 runtime tools.",
    }


def test_capability_registry_snapshot_falls_back_to_first_item_when_selection_missing() -> None:
    catalog = ToolCatalog()

    snapshot = build_capability_registry_snapshot(
        catalog=catalog,
        request=CapabilityRegistryRequest(
            config_data={"tools": {"mcpServers": {}}},
            probe_results={},
            query="",
            source_filter="builtin",
            selected_id="missing:item",
        ),
    )

    assert snapshot.items
    assert snapshot.selected_id == snapshot.items[0]["id"]
    assert snapshot.selected_item["id"] == snapshot.items[0]["id"]
    assert snapshot.overview["availableCount"] >= 1
    assert snapshot.overview["exposureDomainOptions"][0]["key"] == "core"
    assert snapshot.overview["exposureDomainOptions"][0]["locked"] is True
    assert snapshot.overview["exposureDomainOptions"][0]["requiredToolCount"] >= 1


def test_capability_registry_overview_reinserts_core_domain() -> None:
    catalog = ToolCatalog()

    snapshot = build_capability_registry_snapshot(
        catalog=catalog,
        request=CapabilityRegistryRequest(
            config_data={"tools": {"toolExposure": {"mode": "off", "domains": ["web_research"]}}},
            probe_results={},
            query="",
            source_filter="builtin",
            selected_id="",
        ),
    )

    assert snapshot.overview["toolExposureDomains"] == ["core", "web_research"]


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
