from __future__ import annotations

from pathlib import Path

from bao.agent.tool_catalog import ToolCatalog
from bao.browser import BrowserCapabilityState


def _item_by_id(items: list[dict[str, object]], item_id: str) -> dict[str, object]:
    for item in items:
        if item.get("id") == item_id:
            return item
    raise AssertionError(f"Missing item: {item_id}")


def test_tool_catalog_builds_builtin_and_mcp_items(monkeypatch) -> None:
    catalog = ToolCatalog()
    monkeypatch.setattr(
        "bao.agent.tool_catalog.get_browser_capability_state",
        lambda *, enabled=True: BrowserCapabilityState(
            enabled=enabled,
            available=enabled,
            runtime_ready=enabled,
            runtime_root="/runtime/browser",
            runtime_source="bundled",
            profile_path="/data/browser/profile",
            agent_browser_home_path="/runtime/browser/node_modules/agent-browser",
            agent_browser_path="/runtime/browser/bin/agent-browser",
            browser_executable_path="/runtime/browser/chrome",
            reason="ready" if enabled else "disabled",
            detail="Managed browser runtime is ready."
            if enabled
            else "Browser automation is disabled by config.",
        ),
    )
    config_data = {
        "tools": {
            "web": {
                "browser": {"enabled": True},
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
    assert web_item["statusLabel"] == "Search + browser"
    assert web_item["displayName"] == {"zh": "网页检索", "en": "Web Retrieval"}
    assert web_item["displaySummary"]["zh"] == "搜索网页、抓取 URL，并在需要时驱动浏览器。"
    assert web_item["displayDetail"]["en"].startswith("This family combines web search")
    assert web_item["statusDetailDisplay"]["zh"] == "网页搜索 provider 和托管浏览器 runtime 都已就绪。"
    assert web_item["iconSource"] == "../resources/icons/vendor/iconoir/page-search.svg"
    assert web_item["configValues"]["browserEnabled"] is True
    assert web_item["configValues"]["browserAvailable"] is True
    assert web_item["configValues"]["browserProfilePath"] == "/data/browser/profile"
    assert desktop_item["status"] == "disabled"
    assert desktop_item["statusDetailDisplay"]["en"] == "Desktop control is currently disabled."
    assert figma_item["status"] == "healthy"
    assert figma_item["includedTools"] == ["get_file", "get_comments"]
    assert figma_item["displayName"] == {"zh": "figma", "en": "figma"}
    assert figma_item["statusDetailDisplay"]["zh"] == "握手成功，已发现 2 个运行时工具"
    assert broken_item["status"] == "needs_setup"
    assert broken_item["statusDetailDisplay"]["en"] == "Add a command or URL, then test the connection."


def test_tool_catalog_overview_counts_attention_and_runtime(monkeypatch) -> None:
    catalog = ToolCatalog()
    monkeypatch.setattr(
        "bao.agent.tool_catalog.get_browser_capability_state",
        lambda *, enabled=True: BrowserCapabilityState(
            enabled=enabled,
            available=False,
            runtime_ready=False,
            runtime_root="",
            runtime_source="missing",
            profile_path="/data/browser/profile",
            agent_browser_home_path="",
            agent_browser_path="",
            browser_executable_path="",
            reason="runtime_missing" if enabled else "disabled",
            detail="Managed browser runtime is not bundled yet."
            if enabled
            else "Browser automation is disabled by config.",
        ),
    )
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


def test_tools_workspace_consumes_catalog_display_fields() -> None:
    text = (
        Path(__file__).resolve().parents[1] / "app" / "qml" / "ToolsWorkspace.qml"
    ).read_text(encoding="utf-8")

    assert "function localizedText(value, fallback)" in text
    assert "return localizedText(item.displayName, item.name || \"\")" in text
    assert "return localizedText(item.displaySummary, item.summary || \"\")" in text
    assert "return localizedText(item.displayDetail, item.detail || item.summary || \"\")" in text
    assert "return localizedText(item.statusDetailDisplay, item.statusDetail || \"\")" in text
    assert "return String(item.iconSource || \"../resources/icons/sidebar-tools.svg\")" in text
    assert 'case "builtin:' not in text


def test_tool_catalog_exposes_localized_display_fields_for_workspace() -> None:
    catalog = ToolCatalog()

    items = catalog.list_items({"tools": {"mcpServers": {"demo": {"command": "uvx"}}}}, {})

    exec_item = _item_by_id(items, "builtin:exec")
    mcp_item = _item_by_id(items, "mcp:demo")

    assert exec_item["displayName"] == {"zh": "终端执行", "en": "Terminal Exec"}
    assert exec_item["displaySummary"] == {
        "zh": "在运行主机上执行命令，并受超时与沙箱策略约束。",
        "en": "Run shell commands on the runtime host with sandbox controls.",
    }
    assert exec_item["displayDetail"] == {
        "zh": "Exec 是本机命令桥。你可以在这里控制超时、PATH 追加、沙箱模式与工作区边界。",
        "en": "Exec is the bridge to local shell workflows. Its scope is shaped by timeout, sandbox mode, and workspace restrictions.",
    }
    assert exec_item["statusDetailDisplay"] == {
        "zh": "命令执行受沙箱和工作区边界约束。",
        "en": "Command execution is governed by sandbox and workspace boundaries.",
    }
    assert str(exec_item["iconSource"]).endswith("/computer.svg")
    assert mcp_item["displayName"] == {"zh": "demo", "en": "demo"}
    assert mcp_item["displaySummary"] == {
        "zh": "外部 MCP 服务定义。",
        "en": "External MCP server definition.",
    }
