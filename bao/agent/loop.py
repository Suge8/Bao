"""Agent loop: the core processing engine."""

import asyncio
import inspect
import json
import re
import shutil
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, cast, overload
from urllib.parse import urlsplit

import json_repair
from loguru import logger

from bao.agent.context import ContextBuilder
from bao.agent.subagent import SubagentManager
from bao.agent.tools.coding_agent_base import BaseCodingAgentTool, BaseCodingDetailsTool
from bao.agent.tools.cron import CronTool
from bao.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from bao.agent.tools.memory import ForgetTool, RememberTool, UpdateMemoryTool
from bao.agent.tools.message import MessageTool
from bao.agent.tools.registry import ToolRegistry
from bao.agent.tools.shell import ExecTool
from bao.agent.tools.spawn import SpawnTool
from bao.agent.tools.task_status import CancelTaskTool, CheckTasksTool
from bao.agent.tools.web import WebFetchTool, WebSearchTool
from bao.bus.events import InboundMessage, OutboundMessage
from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider
from bao.session.manager import Session, SessionManager

if TYPE_CHECKING:
    from bao.agent.artifacts import ArtifactStore
    from bao.config.schema import Config, EmbeddingConfig, ExecToolConfig, WebSearchConfig
    from bao.cron.service import CronService


_ERROR_KEYWORDS = ("error:", "traceback", "failed", "exception", "permission denied")


class AgentLoop:
    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        memory_window: int = 50,
        search_config: "WebSearchConfig | None" = None,
        exec_config: "ExecToolConfig | None" = None,
        cron_service: "CronService | None" = None,
        embedding_config: "EmbeddingConfig | None" = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict[str, Any] | None = None,
        available_models: list[str] | None = None,
        config: "Config | None" = None,
    ):
        from bao.config.schema import ExecToolConfig

        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.available_models = list(available_models) if available_models else []
        if self.model and self.model not in self.available_models:
            self.available_models.insert(0, self.model)
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_window = memory_window
        self.search_config = search_config
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.embedding_config = embedding_config
        self.restrict_to_workspace = restrict_to_workspace
        self._config = config

        self.context = ContextBuilder(workspace, embedding_config=embedding_config)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        # Context management config
        _cm = config.agents.defaults if config else None
        self._ctx_mgmt: str = _cm.context_management if _cm else "observe"
        self._tool_offload_chars: int = _cm.tool_output_offload_chars if _cm else 8000
        self._tool_preview_chars: int = _cm.tool_output_preview_chars if _cm else 3000
        self._tool_hard_chars: int = _cm.tool_output_hard_chars if _cm else 6000
        self._compact_bytes: int = _cm.context_compact_bytes_est if _cm else 240000
        self._compact_keep_blocks: int = _cm.context_compact_keep_recent_tool_blocks if _cm else 4
        self._artifact_retention_days: int = _cm.artifact_retention_days if _cm else 7
        self._artifact_cleanup_done = False
        _tools_cfg = getattr(config, "tools", None) if config else None
        self._image_generation_config = (
            getattr(_tools_cfg, "image_generation", None) if _tools_cfg else None
        )
        self._desktop_config = (
            getattr(_tools_cfg, "desktop", None) if _tools_cfg else None
        )
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            search_config=search_config,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
            max_iterations=self.max_iterations,
            context_management=self._ctx_mgmt,
            tool_output_offload_chars=self._tool_offload_chars,
            tool_output_preview_chars=self._tool_preview_chars,
            tool_output_hard_chars=self._tool_hard_chars,
            context_compact_bytes_est=self._compact_bytes,
            context_compact_keep_recent_tool_blocks=self._compact_keep_blocks,
            artifact_retention_days=self._artifact_retention_days,
            memory_store=self.context.memory,
            image_generation_config=self._image_generation_config,
            desktop_config=self._desktop_config,
        )

        self._running = False
        self._mcp_servers = mcp_servers or {}
        tools_cfg = _tools_cfg
        raw_mcp_max_tools = getattr(tools_cfg, "mcp_max_tools", 50)
        self._mcp_max_tools = (
            max(raw_mcp_max_tools, 0)
            if (isinstance(raw_mcp_max_tools, int) and not isinstance(raw_mcp_max_tools, bool))
            else 50
        )
        raw_mcp_slim_schema = getattr(tools_cfg, "mcp_slim_schema", True)
        self._mcp_slim_schema = (
            raw_mcp_slim_schema if isinstance(raw_mcp_slim_schema, bool) else True
        )
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connect_succeeded = False
        self._mcp_connecting = False
        self._consolidating: set[str] = set()  # Session keys with consolidation in progress
        self._active_tasks: dict[str, list[asyncio.Task[None]]] = {}  # session_key -> tasks
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._session_generations: dict[str, int] = {}
        self._session_running_task: dict[str, asyncio.Task[None]] = {}
        self._interrupted_task_ids: set[int] = set()
        self._last_tool_budget: dict[str, int] = {
            "offloaded_count": 0,
            "offloaded_chars": 0,
            "clipped_count": 0,
            "clipped_chars": 0,
        }
        self._register_default_tools()

        self._utility_model: str | None = None
        self._utility_provider: LLMProvider | None = None
        if config and config.agents.defaults.utility_model:
            try:
                from bao.providers import make_provider

                um = config.agents.defaults.utility_model
                self._utility_provider = make_provider(config, um)
                self._utility_model = um
                logger.debug("Utility model configured: {}", um)
            except Exception as e:
                logger.warning("Utility model init failed, falling back to main model: {}", e)

        self._experience_mode = (
            config.agents.defaults.experience_model if config else "none"
        ).lower()
        self.subagents.set_aux_runtime(
            utility_provider=self._utility_provider,
            utility_model=self._utility_model,
            experience_mode=self._experience_mode,
        )

        # Callback for system message responses (subagent completion, etc.)
        # Desktop/CLI can register this to receive async notifications.
        self.on_system_response: Callable[[OutboundMessage], Awaitable[None]] | None = None

    def _register_default_tools(self) -> None:
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        self.tools.register(ReadFileTool(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(WriteFileTool(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(EditFileTool(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(ListDirTool(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(
            ExecTool(
                working_dir=str(self.workspace),
                timeout=self.exec_config.timeout,
                restrict_to_workspace=self.restrict_to_workspace,
                path_append=self.exec_config.path_append,
                sandbox_mode=self.exec_config.sandbox_mode,
            )
        )
        coding_agents: list[str] = []
        if shutil.which("opencode"):
            from bao.agent.tools.opencode import OpenCodeDetailsTool, OpenCodeTool

            self.tools.register(OpenCodeTool(workspace=self.workspace, allowed_dir=allowed_dir))
            self.tools.register(OpenCodeDetailsTool())
            coding_agents.append("`opencode`")
        if shutil.which("codex"):
            from bao.agent.tools.codex import CodexDetailsTool, CodexTool

            self.tools.register(CodexTool(workspace=self.workspace, allowed_dir=allowed_dir))
            self.tools.register(CodexDetailsTool())
            coding_agents.append("`codex`")
        if shutil.which("claude"):
            from bao.agent.tools.claudecode import ClaudeCodeDetailsTool, ClaudeCodeTool

            self.tools.register(ClaudeCodeTool(workspace=self.workspace, allowed_dir=allowed_dir))
            self.tools.register(ClaudeCodeDetailsTool())
            coding_agents.append("`claudecode`")
        if coding_agents:
            names = ", ".join(coding_agents)
            self.context.tool_hints.append(
                f"- Coding agents ({names}): AST-aware code search/explore/edit/debug. "
                "Route via `spawn` (non-blocking; subagents have access). "
                "Skills: skills/<tool>/SKILL.md"
            )
        # Image generation (conditional: only when API key is configured)
        if self._image_generation_config and self._image_generation_config.api_key:
            from bao.agent.tools.image_gen import ImageGenTool

            self.tools.register(ImageGenTool(
                api_key=self._image_generation_config.api_key,
                model=self._image_generation_config.model,
                base_url=self._image_generation_config.base_url,
            ))
            self.context.tool_hints.append(
                "- generate_image: create images from text. "
                "Send result via message(media=[path])."
            )
        search_tool = WebSearchTool(search_config=self.search_config)
        has_brave = bool(search_tool.brave_key)
        has_tavily = bool(search_tool.tavily_key)
        has_exa = bool(search_tool.exa_key)
        if has_brave or has_tavily or has_exa:
            providers = [
                p
                for p, ok in [("tavily", has_tavily), ("brave", has_brave), ("exa", has_exa)]
                if ok
            ]
            logger.info("web_search enabled ({})", ", ".join(providers))
            self.tools.register(search_tool)
            self.context.tool_hints.append(
                "- web_search: prefer over web_fetch for finding information. web_fetch only for known URLs."
            )
        self.tools.register(WebFetchTool())
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.context.tool_hints.append(
            "- message: cross-channel delivery only. Normal replies use direct text."
        )
        self.tools.register(SpawnTool(manager=self.subagents))
        self.tools.register(CheckTasksTool(manager=self.subagents))
        self.tools.register(CancelTaskTool(manager=self.subagents))
        self.context.tool_hints.append(
            "- spawn: delegate multi-step, cross-file, or time-consuming work. Keep main loop short."
        )
        mem = self.context.memory
        self.tools.register(RememberTool(memory=mem))
        self.tools.register(ForgetTool(memory=mem))
        self.tools.register(UpdateMemoryTool(memory=mem))
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))
        # Desktop automation (conditional: enabled in config + deps available)
        if self._desktop_config and self._desktop_config.enabled:
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

                self.tools.register(ScreenshotTool())
                self.tools.register(ClickTool())
                self.tools.register(TypeTextTool())
                self.tools.register(KeyPressTool())
                self.tools.register(ScrollTool())
                self.tools.register(DragTool())
                self.tools.register(GetScreenInfoTool())
                self.context.tool_hints.append(
                    "- Desktop automation (screenshot/click/type_text/key_press/scroll/drag/"
                    "get_screen_info): control the desktop. Use screenshot+get_screen_info "
                    "first to see the screen, then click/type to interact."
                )
                logger.info("desktop automation tools enabled")
            except ImportError:
                logger.warning(
                    "desktop automation enabled but deps missing. "
                    "Install: uv sync --extra desktop-automation"
                )

    async def _connect_mcp(self) -> None:
        if (
            self._mcp_connected
            or self._mcp_connect_succeeded
            or self._mcp_connecting
            or not self._mcp_servers
        ):
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
        except Exception as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
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

    def _set_tool_context(
        self,
        channel: str,
        chat_id: str,
        message_id: str | None = None,
        session_key: str | None = None,
    ) -> None:
        if (t := self.tools.get("message")) and isinstance(t, MessageTool):
            t.set_context(channel, chat_id, message_id)
        if (t := self.tools.get("spawn")) and isinstance(t, SpawnTool):
            t.set_context(channel, chat_id, session_key=session_key)
        if (t := self.tools.get("cron")) and isinstance(t, CronTool):
            t.set_context(channel, chat_id)
        for name in (
            "opencode",
            "opencode_details",
            "codex",
            "codex_details",
            "claudecode",
            "claudecode_details",
        ):
            t = self.tools.get(name)
            if t and isinstance(t, (BaseCodingAgentTool, BaseCodingDetailsTool)):
                t.set_context(channel, chat_id, session_key=session_key)

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    @staticmethod
    def _short_hint_arg(value: str, max_len: int = 72) -> str:
        text = value.strip().replace("\n", " ")
        if not text:
            return ""

        if text.startswith(("http://", "https://")):
            parts = urlsplit(text)
            host = f"{parts.scheme}://{parts.netloc}"
            segments = [seg for seg in parts.path.split("/") if seg]
            if not segments:
                return host
            if len(segments) == 1:
                compact = f"{host}/{segments[0]}"
            elif len(segments) == 2:
                compact = f"{host}/{segments[0]}/{segments[1]}"
            else:
                compact = f"{host}/{segments[0]}/.../{segments[-1]}"
            if len(compact) <= max_len:
                return compact
            keep = max_len - len(host) - 2
            keep = max(8, keep)
            return f"{host}/{segments[0][:keep]}..."

        if len(text) <= max_len:
            return text

        cut = text[: max_len - 1]
        split_at = max(cut.rfind(" "), cut.rfind("/"), cut.rfind("_"), cut.rfind("-"))
        if split_at >= 16:
            return f"{cut[:split_at]}..."
        return f"{cut}..."

    @staticmethod
    def _tool_hint(tool_calls: list[Any]) -> str:
        def _fmt(tc: Any) -> str:
            val = next(iter(tc.arguments.values()), None) if tc.arguments else None
            if not isinstance(val, str):
                return tc.name
            short = AgentLoop._short_hint_arg(val)
            return f'{tc.name}("{short}")' if short else tc.name

        return ", ".join(_fmt(tc) for tc in tool_calls)

    @overload
    async def _run_agent_loop(
        self,
        initial_messages: list[dict[str, Any]],
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_tool_hint: Callable[[str], Awaitable[None]] | None = None,
        artifact_session_key: str | None = None,
        return_interrupt: Literal[False] = False,
    ) -> tuple[str | None, list[str], list[str], int, list[str]]: ...

    @overload
    async def _run_agent_loop(
        self,
        initial_messages: list[dict[str, Any]],
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_tool_hint: Callable[[str], Awaitable[None]] | None = None,
        artifact_session_key: str | None = None,
        return_interrupt: Literal[True] = True,
    ) -> tuple[str | None, list[str], list[str], int, list[str], bool]: ...

    async def _run_agent_loop(
        self,
        initial_messages: list[dict[str, Any]],
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_tool_hint: Callable[[str], Awaitable[None]] | None = None,
        artifact_session_key: str | None = None,
        return_interrupt: bool = False,
    ) -> (
        tuple[str | None, list[str], list[str], int, list[str]]
        | tuple[str | None, list[str], list[str], int, list[str], bool]
    ):
        messages = list(initial_messages)
        iteration = 0
        final_content = None
        tools_used: list[str] = []
        tool_trace: list[str] = []
        reasoning_snippets: list[str] = []
        interrupted = False
        consecutive_errors = 0
        total_errors = 0
        failed_directions: list[str] = []
        last_state_attempt_at = 0
        last_state_text: str | None = None
        current_task = asyncio.current_task()
        current_task_id = id(current_task) if current_task else None
        user_request = next(
            (
                m["content"]
                for m in reversed(initial_messages)
                if m.get("role") == "user" and isinstance(m.get("content"), str)
            ),
            "",
        )

        # Layer 1: construct artifact store for tool output offloading
        from bao.agent.artifacts import ArtifactStore, apply_tool_output_budget

        _artifact_store: ArtifactStore | None = (
            ArtifactStore(
                self.workspace,
                artifact_session_key or "main_loop",
                self._artifact_retention_days,
            )
            if self._ctx_mgmt in ("auto", "aggressive")
            else None
        )
        tool_budget = {
            "offloaded_count": 0,
            "offloaded_chars": 0,
            "clipped_count": 0,
            "clipped_chars": 0,
        }

        while iteration < self.max_iterations:
            iteration += 1

            if current_task_id is not None and current_task_id in self._interrupted_task_ids:
                interrupted = True
                break

            steps_since_attempt = len(tool_trace) - last_state_attempt_at
            if steps_since_attempt >= 5 and len(tool_trace) >= 5:
                state = await self._compress_state(
                    tool_trace, reasoning_snippets, failed_directions, last_state_text
                )
                last_state_attempt_at = len(tool_trace)
                if state:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"[State after {len(tool_trace)} steps]\n{state}\n\nUse this state freely — adopt useful parts, ignore irrelevant ones, and prioritize unexplored branches.",
                        }
                    )
                    last_state_text = state

            if len(tool_trace) >= 8 and len(tool_trace) % 4 == 0:
                if await self._check_sufficiency(user_request, tool_trace):
                    messages.append(
                        {
                            "role": "user",
                            "content": "You now have sufficient information. Provide your final answer.",
                        }
                    )

            if self._ctx_mgmt in ("auto", "aggressive"):
                try:
                    approx_bytes = len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))
                except Exception:
                    approx_bytes = 0
                if approx_bytes >= self._compact_bytes:
                    messages = self._compact_messages(
                        messages=messages,
                        initial_messages=initial_messages,
                        last_state_text=last_state_text,
                        artifact_store=_artifact_store,
                    )

            # Signal new iteration to desktop UI so it can split bubbles
            if iteration > 1 and on_progress:
                await on_progress("\x00")

            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                on_progress=on_progress,
                source="main",
            )
            # Strip _image base64 from messages after provider has processed them
            for _m in messages:
                _m.pop("_image", None)

            logger.debug(
                "LLM response: model={}, has_tool_calls={}, tool_count={}, finish_reason={}",
                self.model,
                response.has_tool_calls,
                len(response.tool_calls),
                response.finish_reason,
            )

            if response.has_tool_calls:
                clean = self._strip_think(response.content)
                if clean:
                    reasoning_snippets.append(clean[:200])
                if on_tool_hint:
                    await on_tool_hint(self._tool_hint(response.tool_calls))

                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages,
                    response.content,
                    tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )

                error_feedback: str | None = None
                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info("Tool call: {}({})", tool_call.name, args_str[:200])
                    raw_result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    result_text = raw_result if isinstance(raw_result, str) else str(raw_result)
                    result, budget_event = apply_tool_output_budget(
                        store=_artifact_store,
                        tool_name=tool_call.name,
                        tool_call_id=tool_call.id,
                        result=result_text,
                        offload_chars=self._tool_offload_chars,
                        preview_chars=self._tool_preview_chars,
                        hard_chars=self._tool_hard_chars,
                        ctx_mgmt=self._ctx_mgmt,
                    )
                    if budget_event.offloaded:
                        tool_budget["offloaded_count"] += 1
                        tool_budget["offloaded_chars"] += budget_event.offloaded_chars
                    if budget_event.hard_clipped:
                        tool_budget["clipped_count"] += 1
                        tool_budget["clipped_chars"] += budget_event.hard_clipped_chars
                    # Detect screenshot image marker → inject as multimodal
                    _screenshot_image_b64: str | None = None
                    if isinstance(result, str) and result.startswith("__SCREENSHOT__:"):
                        _ss_path = result[len("__SCREENSHOT__:"):].strip()
                        try:
                            import base64 as _b64mod
                            with open(_ss_path, "rb") as _sf:
                                _screenshot_image_b64 = _b64mod.b64encode(_sf.read()).decode()
                            result = "[screenshot captured]"
                            import os
                            os.unlink(_ss_path)
                        except Exception as _ss_err:
                            logger.warning("failed to read screenshot {}: {}", _ss_path, _ss_err)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result,
                        image_base64=_screenshot_image_b64,
                    )

                    result_lower = result.lower() if isinstance(result, str) else ""
                    has_error = bool(result_lower) and any(
                        kw in result_lower for kw in _ERROR_KEYWORDS
                    )

                    tool_trace.append(
                        f"{tool_call.name}({args_str[:60]}) → {'ERROR' if has_error else 'ok'}: {(result or '')[:100]}"
                    )

                    if has_error:
                        total_errors += 1
                        consecutive_errors += 1
                        first_arg = (
                            next(iter(tool_call.arguments.values()), "")
                            if tool_call.arguments
                            else ""
                        )
                        failed_directions.append(f"{tool_call.name}({str(first_arg)[:80]})")
                    else:
                        consecutive_errors = 0

                    # Interrupt: yield to pending user message at tool boundary
                    if (
                        current_task_id is not None
                        and current_task_id in self._interrupted_task_ids
                    ):
                        logger.info(
                            "Interrupted at tool boundary in session {}", artifact_session_key
                        )
                        interrupted = True
                        break

                if consecutive_errors >= 3:
                    error_feedback = (
                        "Multiple tool errors occurred. STOP retrying the same approach.\n"
                        f"Failed directions so far: {'; '.join(failed_directions[-5:])}\n"
                        "Try a completely different strategy."
                    )
                elif consecutive_errors > 0:
                    failed_hint = (
                        f"\nAlready tried and failed: {'; '.join(failed_directions[-3:])}"
                        if len(failed_directions) > 1
                        else ""
                    )
                    error_feedback = f"The tool returned an error. Analyze what went wrong and try a different approach.{failed_hint}"
                if error_feedback:
                    messages.append({"role": "user", "content": error_feedback})
                # Break outer loop if interrupted at tool boundary
                if current_task_id is not None and current_task_id in self._interrupted_task_ids:
                    interrupted = True
                    break
            else:
                if current_task_id is not None and current_task_id in self._interrupted_task_ids:
                    interrupted = True
                    break
                final_content = self._strip_think(response.content)
                break

        self._last_tool_budget = tool_budget
        if return_interrupt:
            return (
                final_content,
                tools_used,
                tool_trace,
                total_errors,
                reasoning_snippets,
                interrupted,
            )
        return final_content, tools_used, tool_trace, total_errors, reasoning_snippets

    @staticmethod
    def _dispatch_session_key(msg: InboundMessage) -> str:
        override = msg.metadata.get("session_key")
        if isinstance(override, str) and override:
            return override
        if msg.channel == "system":
            if ":" in msg.chat_id:
                origin_channel, origin_chat_id = msg.chat_id.split(":", 1)
                return f"{origin_channel}:{origin_chat_id}"
            return f"gateway:{msg.chat_id}"
        return msg.session_key

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        self._running = True
        await self._connect_mcp()
        logger.debug("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if (msg.content or "").strip().lower() == "/stop":
                await self._handle_stop(msg)
            else:
                session_key = self._dispatch_session_key(msg)

                task_list = self._active_tasks.get(session_key, [])
                busy_tasks = [t for t in task_list if not t.done()]
                if busy_tasks:
                    self._session_generations[session_key] = (
                        self._session_generations.get(session_key, 0) + 1
                    )
                    for t in busy_tasks:
                        self._interrupted_task_ids.add(id(t))

                    running_task = self._session_running_task.get(session_key)
                    if running_task and not running_task.done():
                        self._interrupted_task_ids.add(id(running_task))

                    cmd = (msg.content or "").strip().lower()
                    if msg.channel != "system" and not cmd.startswith("/"):
                        natural_key = msg.session_key
                        active_override = self.sessions.get_active_session_key(natural_key)
                        key = active_override or natural_key
                        session = self.sessions.get_or_create(key)
                        session.add_message("user", msg.content)
                        self.sessions.save(session)
                        msg.metadata["_pre_saved"] = True

                    logger.info("Soft interrupt requested for busy session {}", session_key)

                task_gen = self._session_generations.get(session_key, 0)
                task = asyncio.create_task(
                    self._dispatch(msg, task_generation=task_gen, dispatch_key=session_key)
                )
                self._active_tasks.setdefault(session_key, []).append(task)
                self._session_locks.setdefault(session_key, asyncio.Lock())

                def _on_done(t: asyncio.Task[None], k: str = session_key) -> None:
                    task_list = self._active_tasks.get(k)
                    if not task_list:
                        self._interrupted_task_ids.discard(id(t))
                        return
                    try:
                        task_list.remove(t)
                    except ValueError:
                        self._interrupted_task_ids.discard(id(t))
                        return
                    self._interrupted_task_ids.discard(id(t))
                    if not task_list:
                        self._active_tasks.pop(k, None)
                        self._session_locks.pop(k, None)
                        self._session_running_task.pop(k, None)

                task.add_done_callback(_on_done)

    async def _handle_stop(self, msg: InboundMessage) -> None:
        """Cancel all active tasks and subagents for the session (fire-and-forget)."""
        natural_key = self._dispatch_session_key(msg)
        active_key = self.sessions.get_active_session_key(natural_key)
        target_keys = [natural_key]
        if active_key and active_key != natural_key:
            target_keys.append(active_key)

        cancelled = 0
        sub_cancelled = 0
        for target_key in target_keys:
            self._session_generations[target_key] = self._session_generations.get(target_key, 0) + 1

            running_task = self._session_running_task.pop(target_key, None)
            if running_task:
                self._interrupted_task_ids.discard(id(running_task))

            tasks = self._active_tasks.get(target_key, [])
            for t in tasks:
                self._interrupted_task_ids.discard(id(t))
            cancelled += sum(1 for t in tasks if not t.done() and t.cancel())
            if not any(not t.done() for t in tasks):
                self._active_tasks.pop(target_key, None)
                self._session_locks.pop(target_key, None)

            sub_cancelled += await cast(Any, self.subagents).cancel_by_session(
                target_key, wait=False
            )

        total = cancelled + sub_cancelled
        content = f"\u23f9 Stopped {total} task(s)." if total else "No active task to stop."
        await self.bus.publish_outbound(
            OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=content,
            )
        )

    async def _dispatch(
        self, msg: InboundMessage, *, task_generation: int, dispatch_key: str
    ) -> None:
        lock = self._session_locks.setdefault(dispatch_key, asyncio.Lock())
        async with lock:
            current_task = asyncio.current_task()
            if current_task:
                self._session_running_task[dispatch_key] = current_task
            try:
                sig = inspect.signature(self._process_message).parameters
                kwargs: dict[str, Any] = {}
                if "expected_generation" in sig:
                    kwargs["expected_generation"] = task_generation
                if "expected_generation_key" in sig:
                    kwargs["expected_generation_key"] = dispatch_key
                response = await self._process_message(msg, **kwargs)
                if response:
                    if self._session_generations.get(dispatch_key, 0) != task_generation:
                        logger.info(
                            "Dropping stale response for session {} after /stop", dispatch_key
                        )
                        return
                    # Notify callback for system messages (subagent completion)
                    if msg.channel == "system" and self.on_system_response:
                        try:
                            await self.on_system_response(response)
                        except Exception as cb_err:
                            logger.warning("on_system_response callback failed: {}", cb_err)
                    await self.bus.publish_outbound(response)
            except asyncio.CancelledError:
                logger.info("Task cancelled for session {}", dispatch_key)
                raise
            except Exception as e:
                logger.error("Error processing message: {}", e)
                if self._session_generations.get(dispatch_key, 0) != task_generation:
                    logger.info("Suppressing stale error response for session {}", dispatch_key)
                    return
                await self.bus.publish_outbound(
                    OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"Sorry, I encountered an error: {str(e)}",
                    )
                )
            finally:
                if current_task:
                    self._interrupted_task_ids.discard(id(current_task))
                    if self._session_running_task.get(dispatch_key) is current_task:
                        self._session_running_task.pop(dispatch_key, None)

    async def close_mcp(self) -> None:
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None
        self._mcp_connect_succeeded = False
        self._mcp_connected = False

    def stop(self) -> None:
        self._running = False
        logger.info("Agent loop stopping")

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        expected_generation: int | None = None,
        expected_generation_key: str | None = None,
    ) -> OutboundMessage | None:
        if msg.channel == "system":
            return await self._process_system_message(msg)

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        # Layer 1/2: one-time stale artifact cleanup per process lifetime
        if not self._artifact_cleanup_done:
            self._artifact_cleanup_done = True
            try:
                from bao.agent.artifacts import ArtifactStore

                ArtifactStore(
                    self.workspace, "_stale_", self._artifact_retention_days
                ).cleanup_stale()
            except Exception as _e:
                logger.warning("ctx stale cleanup failed: {}", _e)
        natural_key = session_key or msg.session_key
        active_override = self.sessions.get_active_session_key(natural_key)
        key = active_override or natural_key
        session = self.sessions.get_or_create(key)

        # Handle slash commands
        cmd = msg.content.strip().lower()
        if cmd == "/new":
            if session.messages:
                old_messages = session.messages.copy()
                old_key = session.key

                async def _consolidate_old():
                    temp = Session(key=old_key)
                    temp.messages = old_messages
                    await self._consolidate_memory(temp, archive_all=True)

                asyncio.create_task(_consolidate_old())
            idx = len(self.sessions.list_sessions_for(natural_key)) + 1
            name = f"s{idx}"
            while self.sessions.session_exists(f"{natural_key}::{name}"):
                idx += 1
                name = f"s{idx}"
            self._create_and_switch(natural_key, name)
            return self._reply(msg, f"好的，新对话开始啦「{name}」 🐱")
        if cmd == "/delete":
            active = self.sessions.get_active_session_key(natural_key)
            current_key = active or natural_key
            if current_key != natural_key:
                self.sessions.delete_session(current_key)
            else:
                session.clear()
                self.sessions.save(session)
                self.sessions.invalidate(session.key)
            self.sessions.clear_active_session_key(natural_key)
            return self._reply(msg, "已删除当前会话，已切换到默认会话 🗑️")
        if cmd == "/help":
            return self._reply(
                msg,
                "🐈 bao commands:\n"
                "/new — Start a new conversation\n"
                "/stop — Stop the current task\n"
                "/session — Switch between conversations\n"
                "/delete — Delete current conversation\n"
                "/model — Switch model\n"
                "/help — Show available commands",
            )

        if cmd == "/model" or cmd.startswith("/model "):
            return self._handle_model_command(cmd, msg, session)

        if cmd == "/session":
            return self._handle_session_command(msg, natural_key)

        pending = session.metadata.pop("_pending_model_select", None)
        pending_session = session.metadata.pop("_pending_session_select", None)
        if pending and cmd.isdigit():
            return self._switch_model(int(cmd), msg, session)
        if pending_session and cmd.isdigit():
            self.sessions.save(session)
            return self._select_session(int(cmd), msg, natural_key)

        # ── File-driven onboarding state machine ──
        # Stage detection: no INSTRUCTIONS.md → lang_select
        #                 no PERSONA.md     → persona_setup
        #                 both exist        → ready
        from bao.config.loader import (
            LANG_PICKER,
            PERSONA_GREETING,
            detect_onboarding_stage,
            infer_language,
        )

        onboarding_stage = (
            detect_onboarding_stage(self.workspace) if msg.channel != "system" else "ready"
        )
        if onboarding_stage == "lang_select":
            if cmd in ("1", "2"):
                from bao.config.loader import write_heartbeat, write_instructions

                lang = "zh" if cmd == "1" else "en"
                try:
                    write_instructions(self.workspace, lang)
                except Exception as e:
                    logger.warning("Failed to write instructions template: {}", e)
                try:
                    write_heartbeat(self.workspace, lang)
                except Exception as e:
                    logger.warning("Failed to write heartbeat template: {}", e)
                self.context = ContextBuilder(
                    self.workspace, embedding_config=self.embedding_config
                )
                greeting = PERSONA_GREETING[lang]
                session.add_message("assistant", greeting)
                self.sessions.save(session)
                return self._reply(msg, greeting)
            return self._reply(msg, LANG_PICKER)
        if onboarding_stage == "persona_setup":
            lang = infer_language(self.workspace)
            extract_system = (
                "You extract user profile info from casual text. "
                "Return ONLY valid JSON with these keys: "
                "user_name, user_nickname, bot_name, style, role, interests. "
                "Leave empty string for anything not mentioned."
            )
            extract_prompt = (
                f"User's reply to onboarding questions:\n\n{msg.content}\n\n"
                'Return JSON like: {"user_name": "...", "user_nickname": "...", '
                '"bot_name": "...", "style": "...", "role": "", "interests": ""}'
            )
            try:
                profile = await self._call_utility_llm(extract_system, extract_prompt)
            except Exception:
                profile = None
            if profile:
                from bao.config.loader import write_persona_profile

                try:
                    write_persona_profile(self.workspace, lang, profile)
                    self.context = ContextBuilder(
                        self.workspace, embedding_config=self.embedding_config
                    )
                except Exception as e:
                    logger.warning("Failed to write persona profile: {}", e)
            confirm_hint = {
                "zh": "[系统：以上信息已自动保存，无需操作文件。]\n\n",
                "en": "[System: Profile saved automatically. No file operations needed.]\n\n",
            }[lang]
            msg = InboundMessage(
                channel=msg.channel,
                sender_id=msg.sender_id,
                chat_id=msg.chat_id,
                content=f"{confirm_hint}{msg.content}",
                media=msg.media,
                metadata=msg.metadata,
            )
        if len(session.messages) > self.memory_window and session.key not in self._consolidating:
            self._consolidating.add(session.key)

            async def _consolidate_and_unlock():
                try:
                    await self._consolidate_memory(session)
                finally:
                    self._consolidating.discard(session.key)

            asyncio.create_task(_consolidate_and_unlock())

        self._set_tool_context(
            msg.channel,
            msg.chat_id,
            msg.metadata.get("message_id"),
            session_key=key,
        )
        if (t := self.tools.get("message")) and isinstance(t, MessageTool):
            t.start_turn()
        _results = await asyncio.gather(
            asyncio.to_thread(self.context.memory.search_memory, msg.content),
            asyncio.to_thread(self.context.memory.search_experience, msg.content),
            return_exceptions=True,
        )
        related = _results[0] if not isinstance(_results[0], BaseException) else []
        experience = _results[1] if not isinstance(_results[1], BaseException) else []
        initial_messages = self.context.build_messages(
            history=session.get_history(max_messages=self.memory_window),
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
            related_memory=related or None,
            related_experience=experience or None,
            model=self.model,
        )

        if not msg.metadata.get("_pre_saved") and not msg.metadata.get("_ephemeral"):
            session.add_message("user", msg.content)
            self.sessions.save(session)

        async def _bus_progress(content: str) -> None:
            if content == "\x00":
                return
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            await self.bus.publish_outbound(
                OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=content,
                    metadata=meta,
                )
            )

        async def _bus_tool_hint(content: str) -> None:
            logger.debug("Tool hint sent to {}:{}: {}", msg.channel, msg.chat_id, content)
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = True
            await self.bus.publish_outbound(
                OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=content,
                    metadata=meta,
                )
            )

        (
            final_content,
            tools_used,
            tool_trace,
            total_errors,
            reasoning_snippets,
            interrupted,
        ) = await self._run_agent_loop(
            initial_messages,
            on_progress=on_progress or _bus_progress,
            on_tool_hint=_bus_tool_hint,
            artifact_session_key=session.key,
            return_interrupt=True,
        )

        if interrupted:
            logger.info("Interrupted response dropped for session {}", msg.session_key)
            return None

        generation_key = expected_generation_key or msg.session_key
        if (
            expected_generation is not None
            and self._session_generations.get(generation_key, 0) != expected_generation
        ):
            logger.info(
                "Suppressing stale completion before persistence for session {}", generation_key
            )
            return None

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        if (
            expected_generation is not None
            and self._session_generations.get(generation_key, 0) != expected_generation
        ):
            logger.info(
                "Suppressing stale side-effects before persistence for session {}", generation_key
            )
            return None

        if len(tools_used) >= 2 or total_errors > 0:
            asyncio.create_task(
                self._summarize_experience(
                    msg.content,
                    final_content,
                    tools_used,
                    tool_trace,
                    total_errors,
                    reasoning_snippets,
                )
            )

        if len(session.messages) % 10 == 0:
            asyncio.create_task(self._merge_and_cleanup_experiences())

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)

        session.add_message(
            "assistant", final_content, tools_used=tools_used if tools_used else None
        )

        self.sessions.save(session)

        if len(session.messages) == 2 and not session.metadata.get("title"):
            asyncio.create_task(self._generate_session_title(session))

        if (t := self.tools.get("message")) and isinstance(t, MessageTool) and t._sent_in_turn:
            return None

        out_meta = dict(msg.metadata or {})
        if any(self._last_tool_budget.values()):
            out_meta["_tool_budget"] = dict(self._last_tool_budget)

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=out_meta,
        )

    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        logger.info("Processing system message from {}", msg.sender_id)

        if ":" in msg.chat_id:
            origin_channel, origin_chat_id = msg.chat_id.split(":", 1)
        else:
            origin_channel, origin_chat_id = "gateway", msg.chat_id

        session_key = self._dispatch_session_key(msg)
        session = self.sessions.get_or_create(session_key)
        self._set_tool_context(origin_channel, origin_chat_id, session_key=session_key)
        if (t := self.tools.get("message")) and isinstance(t, MessageTool):
            t.start_turn()
        _results = await asyncio.gather(
            asyncio.to_thread(self.context.memory.search_memory, msg.content),
            asyncio.to_thread(self.context.memory.search_experience, msg.content),
            return_exceptions=True,
        )
        related = _results[0] if not isinstance(_results[0], BaseException) else []
        experience = _results[1] if not isinstance(_results[1], BaseException) else []
        initial_messages = self.context.build_messages(
            history=session.get_history(max_messages=self.memory_window),
            current_message=msg.content,
            channel=origin_channel,
            chat_id=origin_chat_id,
            related_memory=related or None,
            related_experience=experience or None,
            model=self.model,
        )
        (
            final_content,
            tools_used,
            tool_trace,
            total_errors,
            reasoning_snippets,
        ) = await self._run_agent_loop(initial_messages, artifact_session_key=session.key)

        if final_content is None:
            final_content = "Background task completed."

        # Experience learning for system messages (same as normal messages)
        if len(tools_used) >= 2 or total_errors > 0:
            asyncio.create_task(
                self._summarize_experience(
                    msg.content,
                    final_content,
                    tools_used,
                    tool_trace,
                    total_errors,
                    reasoning_snippets,
                )
            )

        if len(session.messages) % 10 == 0:
            asyncio.create_task(self._merge_and_cleanup_experiences())

        session.add_message(
            "user", f"[System: {msg.sender_id}] {msg.content}", _source=msg.sender_id
        )
        session.add_message("assistant", final_content)
        self.sessions.save(session)

        # If message tool already sent content, suppress duplicate outbound
        if (t := self.tools.get("message")) and isinstance(t, MessageTool) and t._sent_in_turn:
            return None

        out_meta: dict[str, Any] = dict(msg.metadata or {})
        out_meta["session_key"] = session_key
        if any(self._last_tool_budget.values()):
            out_meta["_tool_budget"] = dict(self._last_tool_budget)

        return OutboundMessage(
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content,
            metadata=out_meta,
        )

    def _handle_model_command(
        self, cmd: str, msg: InboundMessage, session: Session
    ) -> OutboundMessage:
        _, _, arg = cmd.partition(" ")
        if arg.isdigit():
            return self._switch_model(int(arg), msg, session)

        if not self.available_models:
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=f"Current model: `{self.model}`\n\nNo alternative models configured. Add `models` list to config.",
            )

        lines = [f"Current model: `{self.model}`\n"]
        lines += [
            f"  {i}. {m}{' ✓' if m == self.model else ''}"
            for i, m in enumerate(self.available_models, 1)
        ]
        lines.append("\nReply with a number to switch.")

        session.metadata["_pending_model_select"] = True
        self.sessions.save(session)
        return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content="\n".join(lines))

    def _switch_model(self, idx: int, msg: InboundMessage, session: Session) -> OutboundMessage:
        if idx < 1 or idx > len(self.available_models):
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=f"Invalid selection. Choose 1-{len(self.available_models)}.",
            )

        new_model = self.available_models[idx - 1]
        self.model = new_model

        if self._config:
            try:
                from bao.providers import make_provider

                self.provider = make_provider(self._config, new_model)
                self.subagents.provider = self.provider
                self.subagents.model = new_model
            except Exception as e:
                logger.warning("Failed to rebuild provider for {}: {}", new_model, e)

        self.sessions.save(session)
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=f"Model switched to `{self.model}`",
        )

    # ------------------------------------------------------------------
    # /session — multi-conversation switching
    # ------------------------------------------------------------------

    @staticmethod
    def _reply(msg: "InboundMessage", content: str) -> "OutboundMessage":
        return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=content)

    @staticmethod
    def _format_session_name(key: str, natural_key: str) -> str:
        if key == natural_key:
            return "default"
        prefix = f"{natural_key}::"
        return key[len(prefix) :] if key.startswith(prefix) else key

    def _create_and_switch(self, natural_key: str, name: str) -> str:
        key = f"{natural_key}::{name}"
        self.sessions.save(self.sessions.get_or_create(key))
        self.sessions.set_active_session_key(natural_key, key)
        return name

    def _handle_session_command(self, msg: InboundMessage, natural_key: str) -> OutboundMessage:
        sessions = self.sessions.list_sessions_for(natural_key) or [
            {"key": natural_key, "updated_at": None}
        ]
        active = self.sessions.get_active_session_key(natural_key)
        current_key = active or natural_key

        lines = ["📋 会话列表:\n  0. 取消\n"]
        for i, s in enumerate(sessions, 1):
            skey = str(s.get("key") or natural_key)
            metadata = s.get("metadata") or {}
            title = metadata.get("title")
            name = title or self._format_session_name(skey, natural_key)
            marker = " ✓" if skey == current_key else ""
            updated = s.get("updated_at")
            ts = f" ({str(updated)[:16]})" if updated else ""
            lines.append(f"  {i}. {name}{marker}{ts}")
        lines.append("\n输入数字选择，/new 创建新会话")

        default_session = self.sessions.get_or_create(current_key)
        default_session.metadata["_pending_session_select"] = True
        self.sessions.save(default_session)

        return self._reply(msg, "\n".join(lines))

    def _select_session(self, idx: int, msg: InboundMessage, natural_key: str) -> OutboundMessage:
        if idx == 0:
            return self._reply(msg, "已取消 👌")

        sessions = self.sessions.list_sessions_for(natural_key) or [
            {"key": natural_key, "updated_at": None}
        ]

        if idx < 1 or idx > len(sessions):
            return self._reply(msg, f"无效选择，请输入 0-{len(sessions)}")

        selected = sessions[idx - 1]
        selected_key = str(selected.get("key") or natural_key)

        active = self.sessions.get_active_session_key(natural_key)
        current_key = active or natural_key
        if selected_key == current_key:
            return self._reply(msg, "已在当前会话 👌")

        if selected_key == natural_key:
            self.sessions.clear_active_session_key(natural_key)
        else:
            self.sessions.set_active_session_key(natural_key, selected_key)

        metadata = selected.get("metadata") or {}
        title = metadata.get("title")
        name = title or self._format_session_name(selected_key, natural_key)
        return self._reply(msg, f"已切换到会话「{name}」 🔄")

    async def _consolidate_memory(self, session, archive_all: bool = False) -> None:
        memory = self.context.memory

        if archive_all:
            old_messages = session.messages
            keep_count = 0
            logger.info(
                "Memory consolidation (archive_all): {} total messages archived",
                len(session.messages),
            )
        else:
            keep_count = self.memory_window // 2
            if len(session.messages) <= keep_count:
                logger.debug(
                    "Session {}: No consolidation needed (messages={}, keep={})",
                    session.key,
                    len(session.messages),
                    keep_count,
                )
                return

            messages_to_process = len(session.messages) - session.last_consolidated
            if messages_to_process <= 0:
                logger.debug(
                    "Session {}: No new messages to consolidate (last_consolidated={}, total={})",
                    session.key,
                    session.last_consolidated,
                    len(session.messages),
                )
                return

            old_messages = session.messages[session.last_consolidated : -keep_count]
            if not old_messages:
                return
            logger.info(
                "Memory consolidation started: {} total, {} new to consolidate, {} keep",
                len(session.messages),
                len(old_messages),
                keep_count,
            )

        lines = []
        for m in old_messages:
            if not m.get("content"):
                continue
            tools = f" [tools: {', '.join(m['tools_used'])}]" if m.get("tools_used") else ""
            lines.append(
                f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}{tools}: {m['content']}"
            )
        conversation = "\n".join(lines)
        current_memory = memory.read_long_term()

        prompt = f"""You are a memory consolidation agent. Process this conversation and return a JSON object with exactly two keys:

1. "history_entry": A paragraph (2-5 sentences) summarizing the key events/decisions/topics. Start with a timestamp like [YYYY-MM-DD HH:MM].

2. "memory_updates": An object with categorized memory updates. Keys are categories, values are the updated content for that category. Only include categories that have content. Available categories:
   - "preference": User preferences, habits, communication style, likes/dislikes
   - "personal": User identity, location, relationships, personal facts
   - "project": Project context, technical decisions, tools/services, codebase info
   - "general": Other durable facts that don't fit above categories

## Current Long-term Memory
{current_memory or "(empty)"}

## Conversation to Process
{conversation}

Respond with ONLY valid JSON, no markdown fences."""

        try:
            provider = self._utility_provider or self.provider
            model = self._utility_model or self.model
            response = await provider.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a memory consolidation agent. Respond only with valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                model=model,
                source="utility",
            )
            text = (response.content or "").strip()
            if not text:
                logger.warning("Memory consolidation: LLM returned empty response, skipping")
                return
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json_repair.loads(text)
            if not isinstance(result, dict):
                logger.warning(
                    "Memory consolidation: unexpected response type, skipping. Response: {}",
                    text[:200],
                )
                return

            if entry := result.get("history_entry"):
                if not isinstance(entry, str):
                    entry = json.dumps(entry, ensure_ascii=False)
                memory.append_history(entry)
            # Handle categorized memory updates (new) or single update (legacy)
            if updates := result.get("memory_updates"):
                if isinstance(updates, dict):
                    memory.write_categorized_memory(updates)
            elif update := result.get("memory_update"):
                if not isinstance(update, str):
                    update = json.dumps(update, ensure_ascii=False)
                if update != current_memory:
                    memory.write_long_term(update)

            if archive_all:
                session.last_consolidated = 0
            else:
                session.last_consolidated = len(session.messages) - keep_count
            logger.info(
                "Memory consolidation done: {} messages, last_consolidated={}",
                len(session.messages),
                session.last_consolidated,
            )
        except Exception as e:
            logger.error("Memory consolidation failed: {}", e)

    @staticmethod
    def _parse_llm_json(content: str | None) -> dict[str, Any] | None:
        text = (content or "").strip()
        if not text:
            return None
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json_repair.loads(text)
        return result if isinstance(result, dict) else None

    async def _call_utility_llm(self, system: str, prompt: str) -> dict[str, Any] | None:
        provider = self._utility_provider or self.provider
        model = self._utility_model or self.model
        response = await provider.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            model=model,
            temperature=0.3,
            max_tokens=512,
            source="utility",
        )
        return self._parse_llm_json(response.content)

    async def _generate_session_title(self, session: Session) -> None:
        if session.metadata.get("title"):
            return
        user_msg = next((m for m in session.messages if m["role"] == "user"), None)
        assistant_msg = next((m for m in session.messages if m["role"] == "assistant"), None)
        if not user_msg or not assistant_msg:
            return

        user_content = user_msg["content"][:500]
        assistant_content = assistant_msg["content"][:300]

        prompt = (
            "Based on this conversation, generate a very short title (max 20 characters).\n"
            "The title should capture the main topic. Use the same language as the user's message.\n\n"
            f"User: {user_content}\n"
            f"Assistant: {assistant_content}\n\n"
            'Return JSON: {"title": "your title here"}'
        )

        try:
            result = await self._call_utility_llm(
                "You are a conversation title generator. Respond only with valid JSON.",
                prompt,
            )
            if result and (title := result.get("title")):
                title = str(title).strip()[:30]
                session.metadata["title"] = title
                self.sessions.save(session)
                logger.info("Session title generated: {} → {}", session.key, title)
        except Exception as e:
            logger.debug("Session title generation failed: {}", e)

    async def _call_experience_llm(self, system: str, prompt: str) -> dict[str, Any] | None:
        mode = (self._experience_mode or "utility").lower()
        if mode == "none":
            return None

        use_utility = False
        if mode == "main":
            use_utility = False
        elif mode == "utility":
            use_utility = self._utility_provider is not None
        else:
            use_utility = self._utility_provider is not None

        source = "main" if mode == "main" else "utility"
        if use_utility and self._utility_provider is not None:
            provider, model = self._utility_provider, self._utility_model or self.model
        else:
            provider, model = self.provider, self.model

        response = await provider.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            model=model,
            temperature=0.3,
            max_tokens=512,
            source=source,
        )
        return self._parse_llm_json(response.content)

    def _compact_messages(
        self,
        messages: list[dict[str, Any]],
        initial_messages: list[dict[str, Any]],
        last_state_text: str | None,
        artifact_store: "ArtifactStore | None",
    ) -> list[dict[str, Any]]:
        """Layer 2: 保留最近 N 个 tool 成对消息，归档其余。"""
        if artifact_store is not None:
            try:
                artifact_store.archive_json("evicted_messages", "compacted_context", messages)
            except Exception as exc:
                logger.warning("ctx[L2] archive failed: {}", exc)
        tool_blocks: list[list[dict[str, Any]]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                tc_ids = {tc["id"] for tc in msg["tool_calls"]}
                block, j = [msg], i + 1
                while (
                    j < len(messages)
                    and messages[j].get("role") == "tool"
                    and messages[j].get("tool_call_id") in tc_ids
                ):
                    block.append(messages[j])
                    j += 1
                tool_blocks.append(block)
                i = j
            else:
                i += 1
        recent_blocks = tool_blocks[-self._compact_keep_blocks :]
        recent_msgs = [m for block in recent_blocks for m in block]
        state_note = (
            f"\n\n[Compacted context. Previous state:\n{last_state_text}\n]"
            if last_state_text
            else "\n\n[Compacted context: older messages archived.]"
        )
        system_msgs = [m for m in initial_messages if m.get("role") == "system"]
        user_msgs = [m for m in initial_messages if m.get("role") == "user"]
        if user_msgs:
            original_content = str(user_msgs[0].get("content", ""))
            if "[Compacted context" in original_content:
                state_note = ""
            user_msgs = [
                {**user_msgs[0], "content": original_content + state_note},
                *user_msgs[1:],
            ]
        new_messages = system_msgs + user_msgs + recent_msgs
        logger.debug(
            "ctx[L2] compacted: {} -> {} msgs, {} blocks",
            len(messages),
            len(new_messages),
            len(recent_blocks),
        )
        return new_messages

    async def _compress_state(
        self,
        tool_trace: list[str],
        reasoning_snippets: list[str],
        failed_directions: list[str],
        previous_state: str | None = None,
    ) -> str | None:
        if self._experience_mode == "none":
            parts = [f"[Progress] {len(tool_trace)} steps completed"]
            if failed_directions:
                parts.append(f"[Failed] {'; '.join(failed_directions[-3:])}")
            recent = "; ".join(t.split("→")[0].strip() for t in tool_trace[-5:])
            parts.append(f"[Recent] {recent}")
            return "\n".join(parts)

        trace_str = "\n".join(tool_trace[-10:])
        reasoning_str = " | ".join(reasoning_snippets[-5:]) if reasoning_snippets else "none"
        failed_str = "; ".join(failed_directions[-5:]) if failed_directions else "none"
        prev_section = (
            f"\n## Previous State (update this, don't start from scratch)\n{previous_state}"
            if previous_state
            else ""
        )
        has_failures = len(failed_directions) >= 2
        key_count = "4" if has_failures else "3"
        audit_section = ""
        if has_failures:
            audit_section = '\n4. "audit": 1-2 actionable corrections — what specific mistake to avoid and what concrete action to take instead (NOT vague self-criticism). Omit if no clear correction exists.'
        prompt = f"""Compress this agent execution state into a structured summary. Return JSON with exactly {key_count} keys:

1. "conclusions": What has been established so far — key findings, partial answers, verified facts (2-3 sentences)
2. "evidence": Sources consulted, tools used successfully, data gathered (1-2 sentences)
3. "unexplored": Branches mentioned but NOT yet executed, open questions, alternative approaches to try next (1-3 bullet points as a single string){audit_section}

## Execution Trace
{trace_str}

## Reasoning Steps
{reasoning_str[:400]}

## Failed Approaches
{failed_str}{prev_section}

Respond with ONLY valid JSON."""
        try:
            result = await self._call_experience_llm(
                "You are a trajectory compression agent. Respond only with valid JSON.", prompt
            )
            if not result:
                return None
            parts = []
            if c := result.get("conclusions"):
                parts.append(f"[Conclusions] {c}")
            if e := result.get("evidence"):
                parts.append(f"[Evidence] {e}")
            if u := result.get("unexplored"):
                parts.append(f"[Unexplored branches — prioritize these next] {u}")
            if a := result.get("audit"):
                parts.append(f"[Audit — correct these mistakes] {a}")
            return "\n".join(parts) if parts else None
        except Exception as e:
            logger.debug("State compression skipped: {}", e)
            return None

    async def _check_sufficiency(self, user_request: str, tool_trace: list[str]) -> bool:
        if self._experience_mode == "none":
            return False

        trace_summary = "; ".join(t.split("→")[0].strip() for t in tool_trace[-8:])
        prompt = f"""Given the user's request and the tools already executed, is there enough information to provide a complete answer?

User request: {user_request[:300]}
Steps taken: {trace_summary}

Return JSON: {{"sufficient": true}} or {{"sufficient": false}}"""
        try:
            result = await self._call_experience_llm(
                "You are a task completion verifier. Respond only with valid JSON.", prompt
            )
            return bool(result and result.get("sufficient"))
        except Exception:
            return False

    async def _summarize_experience(
        self,
        user_request: str,
        final_response: str,
        tools_used: list[str],
        tool_trace: list[str],
        total_errors: int = 0,
        reasoning_snippets: list[str] | None = None,
    ) -> None:
        memory = self.context.memory
        tools_str = ", ".join(dict.fromkeys(tools_used))
        trace_str = " → ".join(tool_trace) if tool_trace else "none"
        reasoning_str = " | ".join(reasoning_snippets[:5]) if reasoning_snippets else "none"
        prompt = f"""Analyze this completed task and extract reusable lessons. Return a JSON object with exactly six keys:

1. "task": One-sentence description of what the user asked for (max 80 chars)
2. "outcome": "success" or "partial" or "failed"
3. "quality": Integer 1-5 rating of how useful this experience would be for future similar tasks (5=highly reusable strategy, 1=trivial or too specific)
4. "category": One of: "coding", "search", "file", "config", "analysis", "general"
5. "lessons": 1-3 sentences of actionable lessons learned — what worked, what didn't, what to do differently next time. For successful tasks, also extract the winning strategy that should be reused. Focus on strategies and patterns, not task-specific details.
6. "keywords": 2-5 short keywords/phrases for future retrieval, comma-separated (e.g. "git rebase, merge conflict, branch cleanup")

If the task was trivial (simple greeting, factual Q&A, no real problem-solving), return {{"skip": true}}.

## User Request
{user_request[:500]}

## Tools Used
{tools_str}

## Execution Trace
{trace_str}

## Reasoning Steps
{reasoning_str[:600]}

## Final Response (truncated)
{final_response[:800]}

Respond with ONLY valid JSON, no markdown fences."""

        try:
            result = await self._call_utility_llm(
                "You are an experience extraction agent. Respond only with valid JSON.", prompt
            )
            if not result or result.get("skip"):
                return
            task, lessons = result.get("task", ""), result.get("lessons", "")
            if task and lessons:
                outcome = result.get("outcome", "unknown")
                quality = max(1, min(5, int(result.get("quality", 3))))
                category = result.get("category", "general")
                keywords = result.get("keywords", "")
                reasoning_trace = reasoning_str[:300] if reasoning_snippets else ""
                memory.append_experience(
                    task,
                    outcome,
                    lessons,
                    quality=quality,
                    category=category,
                    keywords=keywords,
                    reasoning_trace=reasoning_trace,
                )
                logger.info(
                    "Experience saved: {} [{}] q={} cat={}", task[:60], outcome, quality, category
                )
                if outcome == "failed":
                    await asyncio.to_thread(memory.deprecate_similar, task)
                elif total_errors == 0:
                    await asyncio.to_thread(memory.record_reuse, task, True)
        except Exception as e:
            logger.debug("Experience extraction skipped: {}", e)

    async def _merge_and_cleanup_experiences(self) -> None:
        memory = self.context.memory
        await asyncio.to_thread(memory.cleanup_stale)
        groups = await asyncio.to_thread(memory.get_merge_candidates)
        if not groups:
            return
        for entries in groups[:2]:
            entries_text = "\n---\n".join(entries[:6])
            prompt = f"""Merge these similar experience entries into ONE concise high-level principle. Return a JSON object with:
1. "task": Generalized task description (max 80 chars)
2. "outcome": "success"
3. "quality": 5
4. "category": The shared category
5. "lessons": 2-3 sentences distilling the common pattern/strategy across all entries

## Entries to Merge
{entries_text}

Respond with ONLY valid JSON, no markdown fences."""
            try:
                result = await self._call_utility_llm(
                    "You are an experience consolidation agent. Respond only with valid JSON.",
                    prompt,
                )
                if not result:
                    continue
                task, lessons = result.get("task", ""), result.get("lessons", "")
                if not (task and lessons):
                    continue
                quality = max(1, min(5, int(result.get("quality", 5))))
                category = result.get("category", "general")
                merged = f"Task: {task}\nLessons: {lessons}"
                await asyncio.to_thread(
                    memory.replace_merged, entries[:6], merged, category=category, quality=quality
                )
            except Exception as e:
                logger.debug("Experience merge skipped: {}", e)

    async def process_direct(
        self,
        content: str,
        session_key: str = "gateway:direct",
        channel: str = "gateway",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        ephemeral: bool = False,
    ) -> str:
        await self._connect_mcp()
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
        if ephemeral:
            msg.metadata["_ephemeral"] = True

        response = await self._process_message(
            msg, session_key=session_key, on_progress=on_progress
        )
        return response.content if response else ""
