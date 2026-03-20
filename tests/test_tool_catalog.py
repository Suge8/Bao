from __future__ import annotations

from pathlib import Path

from bao.agent.tool_catalog import ToolCatalog
from bao.browser import BrowserCapabilityState


def _browser_state(*, enabled: bool, available: bool, runtime_ready: bool) -> BrowserCapabilityState:
    return BrowserCapabilityState(
        enabled=enabled,
        available=available,
        runtime_ready=runtime_ready,
        runtime_root="/runtime/browser" if runtime_ready else "",
        runtime_source="bundled" if runtime_ready else "missing",
        profile_path="/data/browser/profile",
        agent_browser_home_path="/runtime/browser/node_modules/agent-browser" if runtime_ready else "",
        agent_browser_path="/runtime/browser/bin/agent-browser" if runtime_ready else "",
        browser_executable_path="/runtime/browser/chrome" if runtime_ready else "",
        reason="ready" if runtime_ready else ("runtime_missing" if enabled else "disabled"),
        detail="Managed browser runtime is ready."
        if runtime_ready
        else (
            "Managed browser runtime is not bundled yet."
            if enabled
            else "Browser automation is disabled by config."
        ),
    )


def _item_by_id(items: list[dict[str, object]], item_id: str) -> dict[str, object]:
    for item in items:
        if item.get("id") == item_id:
            return item
    raise AssertionError(f"Missing item: {item_id}")


def _assert_web_item_ready(web_item: dict[str, object]) -> None:
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


def _assert_mcp_items(figma_item: dict[str, object], broken_item: dict[str, object]) -> None:
    assert figma_item["status"] == "healthy"
    assert figma_item["includedTools"] == ["get_file", "get_comments"]
    assert figma_item["displayName"] == {"zh": "figma", "en": "figma"}
    assert figma_item["statusDetailDisplay"]["zh"] == "握手成功，已发现 2 个运行时工具"
    assert broken_item["status"] == "needs_setup"
    assert broken_item["statusDetailDisplay"]["en"] == "Add a command or URL, then test the connection."


def test_tool_catalog_builds_builtin_and_mcp_items(monkeypatch) -> None:
    catalog = ToolCatalog()
    monkeypatch.setattr(
        "bao.agent.tool_catalog.get_browser_capability_state",
        lambda *, enabled=True: _browser_state(
            enabled=enabled,
            available=enabled,
            runtime_ready=enabled,
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

    _assert_web_item_ready(web_item)
    assert desktop_item["status"] == "disabled"
    assert desktop_item["statusDetailDisplay"]["en"] == "Desktop control is currently disabled."
    _assert_mcp_items(figma_item, broken_item)


def test_tool_catalog_overview_counts_attention_and_runtime(monkeypatch) -> None:
    catalog = ToolCatalog()
    monkeypatch.setattr(
        "bao.agent.tool_catalog.get_browser_capability_state",
        lambda *, enabled=True: _browser_state(
            enabled=enabled,
            available=False,
            runtime_ready=False,
        ),
    )
    config_data = {
        "tools": {
            "toolExposure": {"mode": "off", "domains": ["core", "web_research"]},
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
    assert overview["toolExposureMode"] == "off"
    assert overview["toolExposureDomains"] == ["core", "web_research"]
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
    assert "return String(item.iconSource || labIcon(\"toolbox\"))" in text
    assert "summaryMetrics" in text
    assert "exposureDomainOptions" in text
    assert "runtimeStateDisplay" in text
    assert "overview.observability" in text
    assert 'case "builtin:' not in text


def test_tools_workspace_header_relies_on_summary_metrics_projection() -> None:
    text = (
        Path(__file__).resolve().parents[1] / "app" / "qml" / "ToolsWorkspaceHeader.qml"
    ).read_text(encoding="utf-8")

    assert "model: workspace.summaryMetrics" in text
    assert "function fallbackMetrics()" not in text


def test_tools_workspace_policies_reuses_metric_chip_component() -> None:
    text = (
        Path(__file__).resolve().parents[1] / "app" / "qml" / "ToolsWorkspacePoliciesPane.qml"
    ).read_text(encoding="utf-8")

    assert "delegate: ToolsWorkspaceMetricChip" in text
    assert "showIndicator: false" in text
    assert "readonly property color detailFillColor" in text
    assert "delegate: ToolsWorkspaceDomainCard" in text
    assert 'domains.indexOf("core") === -1' in text


def test_tools_workspace_domain_card_is_reusable_component() -> None:
    text = (
        Path(__file__).resolve().parents[1] / "app" / "qml" / "ToolsWorkspaceDomainCard.qml"
    ).read_text(encoding="utf-8")

    assert "property bool locked: false" in text
    assert "signal pressed()" in text
    assert "ToolsWorkspaceBadge" in text


def test_tools_workspace_metric_chip_collapses_spacing_without_indicator() -> None:
    text = (
        Path(__file__).resolve().parents[1] / "app" / "qml" / "ToolsWorkspaceMetricChip.qml"
    ).read_text(encoding="utf-8")

    assert "spacing: root.showIndicator ? 8 : 0" in text


def test_tools_builtin_exec_detail_explains_default_sandbox_boundary() -> None:
    text = (
        Path(__file__).resolve().parents[1] / "app" / "qml" / "ToolsBuiltinExecDetail.qml"
    ).read_text(encoding="utf-8")

    assert 'model: ["semi-auto", "full-auto", "read-only"]' in text
    assert "ToolsWorkspaceModeCard" in text
    assert 'return workspace.icon("activity")' in text
    assert 'return workspace.icon("play")' in text
    assert 'return workspace.icon("page-search")' in text
    assert "默认模式不会替你自动打开" in text
    assert "This switch stays separate from sandbox mode" in text


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
