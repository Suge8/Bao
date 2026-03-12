from __future__ import annotations

from bao.agent.tool_catalog import ToolCatalog


def _item_by_id(items: list[dict[str, object]], item_id: str) -> dict[str, object]:
    for item in items:
        if item.get("id") == item_id:
            return item
    raise AssertionError(f"Missing item: {item_id}")


def test_tool_catalog_builds_builtin_and_mcp_items() -> None:
    catalog = ToolCatalog()
    config_data = {
        "tools": {
            "web": {
                "search": {
                    "provider": "tavily",
                    "tavilyApiKey": "tvly-demo",
                    "maxResults": 7,
                }
            },
            "desktop": {"enabled": False},
            "mcpServers": {
                "figma": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-figma"],
                    "toolTimeoutSeconds": 45,
                },
                "broken": {},
            },
        }
    }
    probes = {
        "figma": {
            "serverName": "figma",
            "canConnect": True,
            "toolNames": ["get_file", "get_comments"],
            "error": "",
        }
    }

    items = catalog.list_items(config_data, probes)

    web_item = _item_by_id(items, "builtin:web")
    desktop_item = _item_by_id(items, "builtin:desktop")
    figma_item = _item_by_id(items, "mcp:figma")
    broken_item = _item_by_id(items, "mcp:broken")

    assert web_item["status"] == "ready"
    assert web_item["statusLabel"] == "Search ready"
    assert desktop_item["status"] == "disabled"
    assert figma_item["status"] == "healthy"
    assert figma_item["includedTools"] == ["get_file", "get_comments"]
    assert broken_item["status"] == "needs_setup"


def test_tool_catalog_overview_counts_attention_and_runtime() -> None:
    catalog = ToolCatalog()
    config_data = {
        "tools": {
            "toolExposure": {"mode": "auto", "bundles": ["core", "web"]},
            "restrictToWorkspace": True,
            "desktop": {"enabled": True},
            "mcpServers": {
                "healthy": {"command": "uvx", "args": ["mcp-server"]},
                "missing": {},
            },
        }
    }
    probes = {
        "healthy": {
            "serverName": "healthy",
            "canConnect": True,
            "toolNames": ["ping"],
            "error": "",
        }
    }

    items = catalog.list_items(config_data, probes)
    overview = catalog.build_overview(items, config_data)

    assert overview["builtinCount"] >= 1
    assert overview["mcpServerCount"] == 2
    assert overview["runningNowCount"] == 1
    assert overview["attentionCount"] >= 1
    assert overview["toolExposureMode"] == "auto"
    assert overview["toolExposureBundles"] == ["core", "web"]
    assert overview["restrictToWorkspace"] is True
    assert overview["desktopEnabled"] is True
