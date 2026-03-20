from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from bao.agent.tools.agent_browser import AgentBrowserTool
from bao.agent.tools.web import WebFetchTool, WebSearchTool

from ._loop_tool_registry_common import (
    ToolRegistrationOptions,
    register_tool,
    update_tool_metadata,
)
from ._loop_tool_registry_desktop import register_desktop_tools


def register_optional_tools(loop: Any, allowed_dir: Path | None) -> None:
    _register_coding_tools(loop, allowed_dir)
    _register_web_tools(loop, allowed_dir)
    register_desktop_tools(loop)


def _register_coding_tools(loop: Any, allowed_dir: Path | None) -> None:
    from bao.agent.tools.coding_agent import CodingAgentDetailsTool, CodingAgentTool
    from bao.agent.tools.coding_session_store import SessionMetadataCodingSessionStore

    coding_tool = CodingAgentTool(
        workspace=loop.workspace,
        allowed_dir=allowed_dir,
        session_store=SessionMetadataCodingSessionStore(loop.sessions),
    )
    if not coding_tool.available_backends:
        return
    register_tool(
        loop,
        coding_tool,
        ToolRegistrationOptions(
            bundle="code",
            short_hint="Delegate multi-file coding, debugging, and refactoring to a coding agent.",
            aliases=("coding agent", "代码代理", "写代码"),
            keyword_aliases=("code", "repo", "debug", "refactor", "test", "代码", "修复"),
        ),
    )
    register_tool(
        loop,
        CodingAgentDetailsTool(parent=coding_tool),
        ToolRegistrationOptions(
            bundle="code",
            short_hint="Fetch detailed output from a previous coding agent run.",
            aliases=("coding details", "代码详情"),
            keyword_aliases=("details", "stdout", "stderr", "详情"),
            auto_callable=False,
        ),
    )
    if "opencode" not in coding_tool.available_backends:
        return
    oh_my_paths = [
        loop.workspace / ".opencode/oh-my-opencode.jsonc",
        loop.workspace / ".opencode/oh-my-opencode.json",
        Path.home() / ".config/opencode/oh-my-opencode.jsonc",
        Path.home() / ".config/opencode/oh-my-opencode.json",
    ]
    if any(path.exists() for path in oh_my_paths):
        names = ", ".join(coding_tool.available_backends)
        update_tool_metadata(
            loop,
            "coding_agent",
            short_hint=(
                f"Delegate multi-file coding to {names}; use `ulw` prefix for "
                "OpenCode orchestration mode when helpful."
            ),
        )


def _register_web_tools(loop: Any, allowed_dir: Path | None) -> None:
    search_tool = WebSearchTool(search_config=loop.search_config, proxy=loop.web_proxy)
    has_brave = bool(search_tool.brave_key)
    has_tavily = bool(search_tool.tavily_key)
    has_exa = bool(search_tool.exa_key)
    if has_brave or has_tavily or has_exa:
        providers = [
            name
            for name, ok in [("tavily", has_tavily), ("brave", has_brave), ("exa", has_exa)]
            if ok
        ]
        logger.debug("🔍 启用搜索 / search enabled: {}", ", ".join(providers))
        register_tool(
            loop,
            search_tool,
            ToolRegistrationOptions(
                bundle="web",
                short_hint="Search the web for fresh information; prefer this over web_fetch when no URL is given.",
                aliases=("web search", "search web", "搜索网页", "搜新闻", "查新闻"),
                keyword_aliases=("search", "web", "news", "搜索", "搜", "查", "新闻", "资讯", "最新"),
            ),
        )
    register_tool(
        loop,
        WebFetchTool(
            proxy=loop.web_proxy,
            workspace=loop.workspace,
            browser_enabled=loop._web_browser_enabled,
            allowed_dir=allowed_dir,
        ),
        ToolRegistrationOptions(
            bundle="web",
            short_hint="Fetch a known URL and extract readable content.",
            aliases=("web fetch", "open url", "打开网页", "抓网页"),
            keyword_aliases=("url", "link", "fetch", "网页", "链接", "官网"),
        ),
    )
    browser_tool = AgentBrowserTool(
        workspace=loop.workspace,
        enabled=loop._web_browser_enabled,
        allowed_dir=allowed_dir,
    )
    if loop._web_browser_enabled:
        register_tool(
            loop,
            browser_tool,
            ToolRegistrationOptions(
                bundle="web",
                short_hint="Control a browser for interactive pages, forms, DOM snapshots, and login flows.",
                aliases=("agent browser", "browser automation", "浏览器自动化", "浏览器操作"),
                keyword_aliases=("browser", "agent-browser", "click", "fill", "form", "login", "snapshot", "浏览器", "点击", "表单", "登录"),
            ),
        )
