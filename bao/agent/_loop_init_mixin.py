from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from loguru import logger

from bao.agent._loop_init_support import (
    apply_context_management_defaults,
    apply_tool_config_defaults,
    build_loop_init_options,
    build_utility_provider,
    configure_mcp_and_tool_exposure,
    normalize_available_models,
    resolve_agent_defaults,
    resolve_subagent_manager_class,
)
from bao.agent.context import ContextBuilder, ContextBuilderOptions
from bao.agent.memory import MemoryPolicy
from bao.agent.session_run_controller import SessionRunController
from bao.agent.subagent import SubagentAuxRuntimeConfig, SubagentManagerOptions
from bao.agent.subagent import SubagentManager as _DefaultSubagentManager
from bao.agent.tools.registry import ToolRegistry
from bao.runtime_diagnostics import get_runtime_diagnostics_store
from bao.session.manager import SessionManager

from ._tool_exposure_domains import TOOL_EXPOSURE_DOMAINS as _TOOL_EXPOSURE_DOMAINS

if TYPE_CHECKING:
    from bao.bus.queue import MessageBus
    from bao.providers.base import LLMProvider


class LoopInitMixin:
    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        **kwargs: Any,
    ):
        from bao.config.schema import ExecToolConfig

        options = build_loop_init_options(kwargs)
        defaults = resolve_agent_defaults(options.config)
        self._init_base_runtime(
            bus=bus,
            provider=provider,
            workspace=workspace,
            options=options,
            defaults=defaults,
        )
        self.memory_policy = self._resolve_memory_policy(
            options.memory_policy,
            defaults,
            options.memory_window,
            options.config,
        )
        self.memory_window = self.memory_policy.recent_window
        self.exec_config = options.exec_config or ExecToolConfig()
        self._init_context_services(options=options)
        self._init_subagents(bus=bus, provider=provider, workspace=workspace, options=options)
        self._init_runtime_state(options=options)
        self._register_default_tools()
        self._utility_model = None
        self._utility_provider = build_utility_provider(self, options.config)
        self._experience_mode = self.memory_policy.learning_mode.lower()
        self.subagents.set_aux_runtime(
            SubagentAuxRuntimeConfig(
                utility_provider=self._utility_provider,
                utility_model=self._utility_model,
                experience_mode=self._experience_mode,
            )
        )
        self.on_system_response: Callable[[Any], Any] | None = None

    def _init_base_runtime(
        self,
        *,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        options: Any,
        defaults: Any,
    ) -> None:
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.prompt_root = options.prompt_root or workspace
        self.state_root = options.state_root or workspace
        self.profile_id = str(options.profile_id or "")
        self.model = options.model or provider.get_default_model()
        self.available_models = normalize_available_models(
            model=self.model,
            available_models=options.available_models,
        )
        self.max_iterations = options.max_iterations
        self.temperature = options.temperature
        self.max_tokens = options.max_tokens
        self.reasoning_effort = options.reasoning_effort
        self.service_tier = options.service_tier
        self.search_config = options.search_config
        self.web_proxy = options.web_proxy
        self.cron_service = options.cron_service
        self.embedding_config = options.embedding_config
        self.restrict_to_workspace = options.restrict_to_workspace
        self._config = options.config
        self._delivery_sender = None
        apply_context_management_defaults(self, defaults)
        apply_tool_config_defaults(self, options.config)
        self._mcp_servers = dict(options.mcp_servers)
        configure_mcp_and_tool_exposure(self, options.config, set(_TOOL_EXPOSURE_DOMAINS))

    def _init_context_services(self, *, options: Any) -> None:
        self.context = ContextBuilder(
            self.workspace,
            ContextBuilderOptions(
                prompt_root=self.prompt_root,
                state_root=self.state_root,
                embedding_config=options.embedding_config,
                memory_policy=self.memory_policy,
                profile_metadata=options.profile_metadata,
            ),
        )
        self.sessions = options.session_manager or SessionManager(self.state_root)
        self.tools = ToolRegistry()
        self._runtime_diagnostics = get_runtime_diagnostics_store()

    def _init_subagents(
        self,
        *,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        options: Any,
    ) -> None:
        self.subagents = resolve_subagent_manager_class(_DefaultSubagentManager)(
            provider,
            SubagentManagerOptions(
                workspace=workspace,
                bus=bus,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                reasoning_effort=options.reasoning_effort,
                service_tier=options.service_tier,
                search_config=options.search_config,
                web_proxy=options.web_proxy,
                exec_config=self.exec_config,
                restrict_to_workspace=options.restrict_to_workspace,
                max_iterations=self.max_iterations,
                context_management=self._ctx_mgmt,
                tool_output_offload_chars=self._tool_offload_chars,
                tool_output_preview_chars=self._tool_preview_chars,
                tool_output_hard_chars=self._tool_hard_chars,
                context_compact_bytes_est=self._compact_bytes,
                context_compact_keep_recent_tool_blocks=self._compact_keep_blocks,
                artifact_retention_days=self._artifact_retention_days,
                memory_store=self.context.memory,
                memory_policy=self.memory_policy,
                image_generation_config=self._image_generation_config,
                desktop_config=self._desktop_config,
                browser_enabled=self._web_browser_enabled,
                sessions=self.sessions,
            ),
        )

    def _init_runtime_state(self, *, options: Any) -> None:
        self._running = False
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connect_succeeded = False
        self._mcp_connecting = False
        self._consolidating: set[str] = set()
        self._session_runs = SessionRunController()
        self._run_task: asyncio.Task[None] | None = None
        self._title_generation_inflight: set[str] = set()
        self._last_tool_budget = {
            "offloaded_count": 0,
            "offloaded_chars": 0,
            "clipped_count": 0,
            "clipped_chars": 0,
        }
        self._last_tool_observability: dict[str, Any] = {}
        del options

    @staticmethod
    def _resolve_memory_policy(
        memory_policy: MemoryPolicy | None,
        defaults: Any,
        memory_window: int | None,
        config: Any,
    ) -> MemoryPolicy:
        resolved = (
            memory_policy
            if isinstance(memory_policy, MemoryPolicy)
            else MemoryPolicy.from_agent_defaults(defaults)
        )
        effective_recent_window = 50 if memory_window is None and defaults is None else memory_window
        if effective_recent_window is not None:
            resolved = resolved.with_recent_window(effective_recent_window)
        if config is None and not isinstance(memory_policy, MemoryPolicy):
            return resolved.with_learning_mode("none")
        return resolved

    @property
    def _running(self) -> bool:
        return bool(getattr(self, "_running_state", False))

    @_running.setter
    def _running(self, value: bool) -> None:
        normalized = bool(value)
        previous = bool(getattr(self, "_running_state", False))
        self._running_state = normalized
        if normalized or previous == normalized:
            return
        run_task = getattr(self, "_run_task", None)
        if run_task and not run_task.done() and run_task is not asyncio.current_task():
            run_task.cancel()

    async def _connect_mcp(self) -> None:
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from bao.agent.tools.mcp import connect_mcp_servers

        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            registered, connected_servers = await connect_mcp_servers(
                self._mcp_servers,
                self.tools,
                self._mcp_stack,
                max_tools=self._mcp_max_tools,
                slim_schema=self._mcp_slim_schema,
            )
            self._mcp_connect_succeeded = connected_servers > 0
            self._mcp_connected = registered > 0
            if not self._mcp_connected and self._mcp_stack:
                await self._mcp_stack.aclose()
                self._mcp_stack = None
        except Exception as exc:
            logger.error("❌ MCP 连接失败 / MCP connect failed: {}", exc)
            self._mcp_connect_succeeded = False
            self._mcp_connected = False
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except Exception:
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False
