from __future__ import annotations

from typing import Any

from bao.agent.artifacts import ArtifactStore
from bao.agent.capability_registry import build_available_tool_lines
from bao.agent.tools.diagnostics import RuntimeDiagnosticsTool
from bao.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from bao.agent.tools.registry import ToolRegistry
from bao.agent.tools.shell import ExecTool, ExecToolOptions
from bao.agent.tools.web import WebFetchTool, WebSearchTool

from ._subagent_types import ToolSetupResult


class _SubagentToolSetupMixin:
    def _setup_subagent_tools(self, task_id: str, origin: dict[str, str]) -> ToolSetupResult:
        tools = ToolRegistry()
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        channel = origin.get("channel", "hub")
        chat_id = origin.get("chat_id", "direct")
        self._register_core_tools(tools, allowed_dir=allowed_dir, task_id=task_id)
        coding_tool, coding_tools = self._register_coding_tools(
            tools,
            allowed_dir=allowed_dir,
            channel=channel,
            chat_id=chat_id,
            session_key=origin.get("session_key"),
        )
        self._register_optional_image_tool(tools)
        self._register_optional_desktop_tools(tools)
        has_search, has_browser = self._register_web_tools(
            tools,
            allowed_dir=allowed_dir,
            channel=channel,
            chat_id=chat_id,
            session_key=origin.get("session_key"),
        )
        return ToolSetupResult(
            tools=tools,
            coding_tool=coding_tool,
            coding_tools=coding_tools,
            has_search=has_search,
            has_browser=has_browser,
        )

    def _register_core_tools(self, tools: ToolRegistry, *, allowed_dir, task_id: str) -> None:
        tools.register(ReadFileTool(workspace=self.workspace, allowed_dir=allowed_dir))
        tools.register(WriteFileTool(workspace=self.workspace, allowed_dir=allowed_dir))
        tools.register(EditFileTool(workspace=self.workspace, allowed_dir=allowed_dir))
        tools.register(ListDirTool(workspace=self.workspace, allowed_dir=allowed_dir))
        tools.register(
            RuntimeDiagnosticsTool(
                store=self._runtime_diagnostics,
                allowed_sources=("subagent",),
                pinned_session_key=task_id,
                allow_logs=False,
                allow_tool_observability=False,
            )
        )
        tools.register(
            ExecTool(
                ExecToolOptions(
                    working_dir=str(self.workspace),
                    timeout=self.exec_config.timeout,
                    restrict_to_workspace=self.restrict_to_workspace,
                    path_append=self.exec_config.path_append,
                    sandbox_mode=self.exec_config.sandbox_mode,
                )
            )
        )

    def _register_coding_tools(
        self,
        tools: ToolRegistry,
        *,
        allowed_dir,
        channel: str,
        chat_id: str,
        session_key: str | None,
    ) -> tuple[Any, list[str]]:
        from bao.agent.tools.coding_agent import CodingAgentDetailsTool, CodingAgentTool

        coding_tool = CodingAgentTool(workspace=self.workspace, allowed_dir=allowed_dir)
        coding_tools: list[str] = []
        if not coding_tool.available_backends:
            return coding_tool, coding_tools
        coding_details = CodingAgentDetailsTool(parent=coding_tool)
        coding_tool.set_context(channel, chat_id, session_key=session_key)
        coding_details.set_context(channel, chat_id, session_key=session_key)
        tools.register(coding_tool)
        tools.register(coding_details)
        coding_tools.extend(coding_tool.available_backends)
        return coding_tool, coding_tools

    def _register_optional_image_tool(self, tools: ToolRegistry) -> None:
        image_api_key = (
            self.image_generation_config.api_key.get_secret_value()
            if self.image_generation_config
            else ""
        )
        if not self.image_generation_config or not image_api_key:
            return
        from bao.agent.tools.image_gen import ImageGenTool

        tools.register(
            ImageGenTool(
                api_key=image_api_key,
                model=self.image_generation_config.model,
                base_url=self.image_generation_config.base_url,
            )
        )

    def _register_optional_desktop_tools(self, tools: ToolRegistry) -> None:
        if not self.desktop_config or not self.desktop_config.enabled:
            return
        try:
            from bao.agent.tools.desktop import (
                ClickTool,
                DragTool,
                GetScreenInfoTool,
                KeyPressTool,
                ScreenshotTool,
                ScrollTool,
                TypeTextTool,
            )
        except ImportError:
            return
        tools.register(ScreenshotTool())
        tools.register(ClickTool())
        tools.register(TypeTextTool())
        tools.register(KeyPressTool())
        tools.register(ScrollTool())
        tools.register(DragTool())
        tools.register(GetScreenInfoTool())

    def _register_web_tools(
        self,
        tools: ToolRegistry,
        *,
        allowed_dir,
        channel: str,
        chat_id: str,
        session_key: str | None,
    ) -> tuple[bool, bool]:
        from bao.agent.tools.agent_browser import AgentBrowserTool

        search_tool = WebSearchTool(search_config=self.search_config, proxy=self.web_proxy)
        has_search = bool(search_tool.brave_key or search_tool.tavily_key or search_tool.exa_key)
        if has_search:
            tools.register(search_tool)
        web_fetch_tool = WebFetchTool(
            proxy=self.web_proxy,
            workspace=self.workspace,
            browser_enabled=self.browser_enabled,
            allowed_dir=allowed_dir,
        )
        web_fetch_tool.set_context(channel, chat_id, session_key=session_key)
        tools.register(web_fetch_tool)
        browser_tool = AgentBrowserTool(
            workspace=self.workspace,
            enabled=self.browser_enabled,
            allowed_dir=allowed_dir,
        )
        has_browser = False
        if self.browser_enabled:
            browser_tool.set_context(channel, chat_id, session_key=session_key)
            tools.register(browser_tool)
            has_browser = browser_tool.available
        return has_search, has_browser

    def _maybe_cleanup_stale_artifacts(self) -> None:
        if self._artifact_cleanup_done or self._ctx_mgmt not in ("auto", "aggressive"):
            return
        self._artifact_cleanup_done = True
        try:
            ArtifactStore(self.workspace, "_stale_", self._artifact_retention_days).cleanup_stale()
        except Exception as exc:
            from loguru import logger

            logger.debug("subagent ctx stale cleanup failed: {}", exc)

    def _create_subagent_artifact_store(self, task_id: str) -> ArtifactStore | None:
        if self._ctx_mgmt not in ("auto", "aggressive"):
            return None
        return ArtifactStore(self.workspace, f"subagent_{task_id}", self._artifact_retention_days)

    def _build_subagent_tool_exposure_snapshot(
        self,
        *,
        task: str,
        tools: ToolRegistry,
        force_final_response: bool,
    ):
        from bao.agent.tool_exposure import ToolExposureSnapshot

        tool_definitions, slim_schema = tools.get_budgeted_definitions(
            names=None if not force_final_response else set()
        )
        ordered_tool_names = () if force_final_response else tuple(tools.tool_names)
        return ToolExposureSnapshot(
            mode="subagent",
            force_final_response=force_final_response,
            route_text=task,
            ordered_tool_names=ordered_tool_names,
            available_tool_lines=tuple(
                build_available_tool_lines(
                    registry=tools,
                    selected_tool_names=list(ordered_tool_names),
                )
            ),
            tool_definitions=tuple(tool_definitions),
            slim_schema=slim_schema,
        )
