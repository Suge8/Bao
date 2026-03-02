"""Agent loop: the core processing engine."""

import asyncio
import inspect
import json
import re
import tempfile
import uuid
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, cast, overload
from urllib.parse import urlsplit

import json_repair
from loguru import logger

from bao.agent import commands, experience, shared
from bao.agent.context import ContextBuilder
from bao.agent.memory import MEMORY_CATEGORIES, MEMORY_CATEGORY_CAPS
from bao.agent.subagent import SubagentManager
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
from bao.providers.retry import PROGRESS_RESET
from bao.session.manager import Session, SessionManager

if TYPE_CHECKING:
    from bao.agent.artifacts import ArtifactStore
    from bao.config.schema import Config, EmbeddingConfig, ExecToolConfig, WebSearchConfig
    from bao.cron.service import CronService


_ERROR_KEYWORDS = ("error:", "traceback", "failed", "exception", "permission denied")
_TOOL_OBS_LAST_KEY = "_tool_observability_last"
_TOOL_OBS_RECENT_KEY = "_tool_observability_recent"
_TOOL_OBS_RECENT_LIMIT = 20
_TOOL_BUNDLE_CORE = "core"
_TOOL_BUNDLE_WEB = "web"
_TOOL_BUNDLE_DESKTOP = "desktop"
_TOOL_BUNDLE_CODE = "code"
_TOOL_BUNDLES = frozenset(
    {_TOOL_BUNDLE_CORE, _TOOL_BUNDLE_WEB, _TOOL_BUNDLE_DESKTOP, _TOOL_BUNDLE_CODE}
)
_WEB_SIGNAL_TOKENS = (
    "http://",
    "https://",
    "www.",
    "网页",
    "网站",
    "url",
    "搜索",
    "search",
    "crawl",
    "fetch",
    "浏览",
)
_DESKTOP_SIGNAL_TOKENS = (
    "desktop",
    "screen",
    "screenshot",
    "click",
    "type",
    "drag",
    "scroll",
    "键盘",
    "屏幕",
    "截图",
    "点击",
    "输入",
)
_CODE_SIGNAL_TOKENS = (
    "code",
    "repo",
    "git",
    "test",
    "debug",
    "refactor",
    "python",
    "javascript",
    "typescript",
    "bash",
    "文件",
    "代码",
    "脚本",
    "函数",
    "修复",
)
_CORE_TOOL_NAMES = frozenset(
    {
        "message",
        "spawn",
        "check_tasks",
        "cancel_task",
        "remember",
        "forget",
        "update_memory",
        "cron",
        "generate_image",
    }
)
_WEB_TOOL_NAMES = frozenset({"web_search", "web_fetch"})
_DESKTOP_TOOL_NAMES = frozenset(
    {
        "screenshot",
        "click",
        "type_text",
        "key_press",
        "scroll",
        "drag",
        "get_screen_info",
    }
)
_CODE_TOOL_NAMES = frozenset(
    {
        "read_file",
        "write_file",
        "edit_file",
        "list_dir",
        "exec",
        "coding_agent",
        "coding_agent_details",
    }
)

_GREETING_WORDS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "yo",
        "你好",
        "您好",
        "在吗",
        "忙吗",
        "嗯",
        "ok",
        "好",
        "好的",
        "哈喽",
        "嘿",
        "哈",
        "嗨",
    }
)


def _extract_text(content: Any) -> str:
    """Extract text from message content (str or multimodal list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(p.get("text") or "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        )
    return str(content) if content else ""


def _archive_all_signature(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return ""
    tail_ts = str(messages[-1].get("timestamp", ""))
    return f"{len(messages)}:{tail_ts}"


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
        reasoning_effort: str | None = None,
        search_config: "WebSearchConfig | None" = None,
        web_proxy: str | None = None,
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
        self.reasoning_effort = reasoning_effort
        self.search_config = search_config
        self.web_proxy = web_proxy
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
        self._desktop_config = getattr(_tools_cfg, "desktop", None) if _tools_cfg else None
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=reasoning_effort,
            search_config=search_config,
            web_proxy=web_proxy,
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
        tool_exposure_cfg = getattr(tools_cfg, "tool_exposure", None)
        raw_mode = str(getattr(tool_exposure_cfg, "mode", "off") or "off").lower()
        self._tool_exposure_mode = raw_mode if raw_mode in ("off", "auto") else "off"
        raw_bundles = getattr(tool_exposure_cfg, "bundles", None)
        bundles = (
            [str(item).strip().lower() for item in raw_bundles]
            if isinstance(raw_bundles, list)
            else []
        )
        self._tool_exposure_bundles = {item for item in bundles if item in _TOOL_BUNDLES}
        if not self._tool_exposure_bundles:
            self._tool_exposure_bundles = set(_TOOL_BUNDLES)
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connect_succeeded = False
        self._mcp_connecting = False
        self._consolidating: set[str] = set()  # Session keys with consolidation in progress
        self._active_tasks: dict[str, list[asyncio.Task[None]]] = {}  # session_key -> tasks
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._session_generations: dict[str, int] = {}
        self._session_running_task: dict[str, asyncio.Task[None]] = {}
        self._interrupted_tasks: set[asyncio.Task[None]] = set()
        self._title_generation_inflight: set[str] = set()
        self._last_tool_budget: dict[str, int] = {
            "offloaded_count": 0,
            "offloaded_chars": 0,
            "clipped_count": 0,
            "clipped_chars": 0,
        }
        self._last_tool_observability: dict[str, Any] = {}
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
                logger.warning("⚠️ 效用模型初始化失败 / utility init failed: {}", e)

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
        from bao.agent.tools.coding_agent import CodingAgentDetailsTool, CodingAgentTool

        coding_tool = CodingAgentTool(workspace=self.workspace, allowed_dir=allowed_dir)
        if coding_tool.available_backends:
            self.tools.register(coding_tool)
            self.tools.register(CodingAgentDetailsTool(parent=coding_tool))
            names = ", ".join(coding_tool.available_backends)
            self.context.tool_hints.append(
                f"- coding_agent(agent=...): delegate coding tasks to {names}. "
                "Route via `spawn` (non-blocking; subagents have access). "
                "Skill: skills/coding-agent/SKILL.md"
            )
            if "opencode" in coding_tool.available_backends:
                _omo_paths = [
                    self.workspace / ".opencode/oh-my-opencode.jsonc",
                    self.workspace / ".opencode/oh-my-opencode.json",
                    Path.home() / ".config/opencode/oh-my-opencode.jsonc",
                    Path.home() / ".config/opencode/oh-my-opencode.json",
                ]
                if any(p.exists() for p in _omo_paths):
                    self.context.tool_hints.append(
                        "- OhMyOpenCode detected: use `ulw` prefix in opencode prompts "
                        "for enhanced orchestration mode."
                    )
        # Image generation (conditional: only when API key is configured)
        image_api_key = (
            self._image_generation_config.api_key.get_secret_value()
            if self._image_generation_config
            else ""
        )
        if self._image_generation_config and image_api_key:
            from bao.agent.tools.image_gen import ImageGenTool

            self.tools.register(
                ImageGenTool(
                    api_key=image_api_key,
                    model=self._image_generation_config.model,
                    base_url=self._image_generation_config.base_url,
                )
            )
            self.context.tool_hints.append(
                "- generate_image: create images from text. Send result via message(media=[path])."
            )
        search_tool = WebSearchTool(search_config=self.search_config, proxy=self.web_proxy)
        has_brave = bool(search_tool.brave_key)
        has_tavily = bool(search_tool.tavily_key)
        has_exa = bool(search_tool.exa_key)
        if has_brave or has_tavily or has_exa:
            providers = [
                p
                for p, ok in [("tavily", has_tavily), ("brave", has_brave), ("exa", has_exa)]
                if ok
            ]
            logger.info("🔍 启用搜索 / search enabled: {}", ", ".join(providers))
            self.tools.register(search_tool)
            self.context.tool_hints.append(
                "- web_search: prefer over web_fetch for finding information. web_fetch only for known URLs."
            )
        self.tools.register(WebFetchTool(proxy=self.web_proxy))
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.context.tool_hints.append(
            "- message: cross-channel delivery only. Normal replies use direct text."
        )
        self.tools.register(SpawnTool(manager=self.subagents))
        self.tools.register(CheckTasksTool(manager=self.subagents))
        self.tools.register(CancelTaskTool(manager=self.subagents))
        self.context.tool_hints.append(
            "- spawn: delegate multi-step or time-consuming work. Returns task_id for "
            "check_tasks/cancel_task. Pass context_from=<task_id> to give the subagent context "
            "from a previous task's result. When spawning coding tasks, describe clearly — "
            "subagents can use coding tools if available.\n"
            "- check_tasks: use ONLY when the user explicitly asks about task progress. "
            "Do NOT poll proactively or call in a loop."
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
                logger.info("🖥️ 启用桌面 / desktop enabled: desktop automation tools")
            except ImportError:
                logger.warning(
                    "⚠️ 桌面依赖缺失 / desktop deps missing: "
                    "Install: uv sync --extra desktop-automation"
                )

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
        except Exception as e:
            logger.error("❌ MCP 连接失败 / MCP connect failed: {}", e)
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
        message_id: str | int | None = None,
        session_key: str | None = None,
    ) -> None:
        if isinstance(message_id, bool) or message_id is None:
            normalized_message_id = None
        elif isinstance(message_id, (str, int)):
            normalized_message_id = str(message_id)
        else:
            normalized_message_id = None
        if (t := self.tools.get("message")) and isinstance(t, MessageTool):
            t.set_context(channel, chat_id, normalized_message_id)
        if (t := self.tools.get("spawn")) and isinstance(t, SpawnTool):
            t.set_context(channel, chat_id, session_key=session_key)
        if (t := self.tools.get("cron")) and isinstance(t, CronTool):
            t.set_context(channel, chat_id)
        for name in ("coding_agent", "coding_agent_details"):
            t = self.tools.get(name)
            if not t:
                continue
            set_ctx = getattr(t, "set_context", None)
            if callable(set_ctx):
                set_ctx(channel, chat_id, session_key=session_key)

    @staticmethod
    def _latest_user_text(messages: list[dict[str, Any]]) -> str:
        for msg in reversed(messages):
            if msg.get("role") != "user":
                continue
            text = _extract_text(msg.get("content", ""))
            if text:
                return text.lower()
        return ""

    @staticmethod
    def _bundle_for_tool_name(name: str) -> str | None:
        if name in _WEB_TOOL_NAMES:
            return _TOOL_BUNDLE_WEB
        if name in _DESKTOP_TOOL_NAMES:
            return _TOOL_BUNDLE_DESKTOP
        if name in _CODE_TOOL_NAMES:
            return _TOOL_BUNDLE_CODE
        if name in _CORE_TOOL_NAMES:
            return _TOOL_BUNDLE_CORE
        return None

    def _auto_route_bundles(self, user_text: str) -> set[str]:
        bundles = {_TOOL_BUNDLE_CORE}
        if any(token in user_text for token in _WEB_SIGNAL_TOKENS):
            bundles.add(_TOOL_BUNDLE_WEB)
        if any(token in user_text for token in _DESKTOP_SIGNAL_TOKENS):
            bundles.add(_TOOL_BUNDLE_DESKTOP)
        if any(token in user_text for token in _CODE_SIGNAL_TOKENS):
            bundles.add(_TOOL_BUNDLE_CODE)
        return bundles

    def _select_tool_names_for_turn(
        self, initial_messages: list[dict[str, Any]]
    ) -> set[str] | None:
        mode = self._tool_exposure_mode
        if mode == "off":
            return None
        enabled_bundles = self._tool_exposure_bundles
        user_text = self._latest_user_text(initial_messages)
        selected_bundles = self._auto_route_bundles(user_text) & enabled_bundles
        if not selected_bundles:
            selected_bundles = {_TOOL_BUNDLE_CORE} & enabled_bundles
        selected_names: set[str] = set()
        for name in self.tools.tool_names:
            bundle = self._bundle_for_tool_name(name)
            if bundle and bundle in selected_bundles:
                selected_names.add(name)
            elif bundle is None:
                selected_names.add(name)
        return selected_names

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
            args = getattr(tc, "arguments", None)
            if isinstance(args, list):
                args = args[0] if args else None
            if not isinstance(args, dict):
                args = {}
            val = next(iter(args.values()), None) if args else None
            if not isinstance(val, str):
                return tc.name
            short = AgentLoop._short_hint_arg(val)
            return f'{tc.name}("{short}")' if short else tc.name

        return ", ".join(_fmt(tc) for tc in tool_calls)

    _TOOL_INTERRUPT_POLL = 0.2
    _TOOL_CANCEL_TIMEOUT = 5.0  # max seconds to wait for tool cleanup after cancel
    _TOOL_CANCELLED_MSG = "Cancelled by soft interrupt."

    async def _await_tool_with_interrupt(
        self,
        tool_task: asyncio.Task[str],
        current_task_ref: asyncio.Task[None] | None,
    ) -> str:
        """Await tool task with periodic soft-interrupt checks."""
        if current_task_ref is None:
            return await tool_task
        try:
            while not tool_task.done():
                if current_task_ref in self._interrupted_tasks:
                    if tool_task.done():
                        return await tool_task
                    tool_task.cancel()
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(tool_task),
                            timeout=self._TOOL_CANCEL_TIMEOUT,
                        )
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                    except Exception:
                        pass
                    if tool_task.done() and not tool_task.cancelled():
                        try:
                            return tool_task.result()
                        except Exception:
                            pass
                    return self._TOOL_CANCELLED_MSG
                try:
                    return await asyncio.wait_for(
                        asyncio.shield(tool_task), timeout=self._TOOL_INTERRUPT_POLL
                    )
                except asyncio.TimeoutError:
                    continue
            return await tool_task
        except asyncio.CancelledError:
            if not tool_task.done():
                tool_task.cancel()
                try:
                    await asyncio.wait_for(
                        asyncio.shield(tool_task),
                        timeout=self._TOOL_CANCEL_TIMEOUT,
                    )
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                except Exception:
                    pass
            raise

    @staticmethod
    def _estimate_payload_bytes(payload: Any) -> int:
        try:
            return len(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            )
        except Exception:
            return 0

    @staticmethod
    def _estimate_token_count(byte_size: int) -> int:
        if byte_size <= 0:
            return 0
        return (byte_size + 3) // 4

    @staticmethod
    def _safe_rate(numerator: int, denominator: int) -> float | None:
        if denominator <= 0:
            return None
        return round(numerator / denominator, 4)

    def _persist_tool_observability(
        self,
        session: Session,
        *,
        channel: str,
        session_key: str,
    ) -> None:
        if not self._last_tool_observability:
            return
        entry = {
            "timestamp": datetime.now().isoformat(),
            "channel": channel,
            "session_key": session_key,
            **self._last_tool_observability,
        }
        session.metadata[_TOOL_OBS_LAST_KEY] = entry
        raw_recent = session.metadata.get(_TOOL_OBS_RECENT_KEY)
        recent = raw_recent if isinstance(raw_recent, list) else []
        recent.append(entry)
        if len(recent) > _TOOL_OBS_RECENT_LIMIT:
            del recent[:-_TOOL_OBS_RECENT_LIMIT]
        session.metadata[_TOOL_OBS_RECENT_KEY] = recent

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
    ) -> tuple[
        str | None,
        list[str],
        list[str],
        int,
        list[str],
        bool,
        bool,
        list[dict[str, Any]],
    ]: ...

    async def _run_agent_loop(
        self,
        initial_messages: list[dict[str, Any]],
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_tool_hint: Callable[[str], Awaitable[None]] | None = None,
        artifact_session_key: str | None = None,
        return_interrupt: bool = False,
    ) -> (
        tuple[str | None, list[str], list[str], int, list[str]]
        | tuple[
            str | None,
            list[str],
            list[str],
            int,
            list[str],
            bool,
            bool,
            list[dict[str, Any]],
        ]
    ):
        messages = list(initial_messages)
        iteration = 0
        final_content = None
        tools_used: list[str] = []
        tool_trace: list[str] = []
        reasoning_snippets: list[str] = []
        _completed_tool_msgs: list[dict[str, Any]] = []
        provider_error = False
        interrupted = False
        consecutive_errors = 0
        total_errors = 0
        failed_directions: list[str] = []
        total_tool_steps_for_sufficiency = 0
        next_sufficiency_at = 8
        force_final_response = False
        force_final_backoff_used = False
        sufficiency_trace: list[str] = []
        last_state_attempt_at = 0
        last_state_text: str | None = None
        current_task = asyncio.current_task()
        current_task_ref: asyncio.Task[None] | None = current_task
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
        schema_samples = 0
        schema_tool_count_last = 0
        schema_tool_count_max = 0
        schema_bytes_last = 0
        schema_bytes_max = 0
        schema_bytes_total = 0
        tool_calls_ok = 0
        invalid_parameter_errors = 0
        tool_not_found_errors = 0
        execution_errors = 0
        interrupted_tool_calls = 0
        retry_attempts_proxy = 0

        while iteration < self.max_iterations:
            iteration += 1

            if current_task_ref is not None and current_task_ref in self._interrupted_tasks:
                interrupted = True
                break

            steps_since_attempt = len(tool_trace) - last_state_attempt_at
            if steps_since_attempt >= 5 and len(tool_trace) >= 5:
                state = await self._compress_state(
                    tool_trace, reasoning_snippets, failed_directions, last_state_text
                )
                last_state_attempt_at = len(tool_trace)
                if state:
                    steps_before_reset = len(tool_trace)
                    messages.append(
                        {
                            "role": "user",
                            "content": f"[State after {steps_before_reset} steps]\n{state}\n\nUse this state freely — adopt useful parts, ignore irrelevant ones, and prioritize unexplored branches.",
                        }
                    )
                    last_state_text = state
                    # RE-TRAC reset: state becomes the new starting point
                    tool_trace.clear()
                    reasoning_snippets.clear()
                    failed_directions.clear()
                    consecutive_errors = 0
                    last_state_attempt_at = 0

            if total_tool_steps_for_sufficiency >= next_sufficiency_at:
                if await self._check_sufficiency(user_request, sufficiency_trace, last_state_text):
                    messages.append(
                        {
                            "role": "user",
                            "content": "You now have sufficient information. Provide your final answer.",
                        }
                    )
                    force_final_response = True
                while next_sufficiency_at <= total_tool_steps_for_sufficiency:
                    next_sufficiency_at += 4

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
                await on_progress(PROGRESS_RESET)

            _stream_progress = on_progress
            if current_task_ref is not None and on_progress is not None:

                async def _interruptable_progress(chunk: str, _orig=on_progress) -> None:
                    if current_task_ref in self._interrupted_tasks:
                        from bao.providers.retry import StreamInterruptedError

                        raise StreamInterruptedError("soft interrupt during streaming")
                    await _orig(chunk)

                _stream_progress = _interruptable_progress

            selected_tool_names = self._select_tool_names_for_turn(initial_messages)
            current_tools = (
                []
                if force_final_response
                else self.tools.get_definitions(names=selected_tool_names)
            )
            if current_tools and schema_samples == 0:
                current_schema_bytes = self._estimate_payload_bytes(current_tools)
                schema_samples += 1
                schema_tool_count_last = len(current_tools)
                schema_tool_count_max = max(schema_tool_count_max, schema_tool_count_last)
                schema_bytes_last = current_schema_bytes
                schema_bytes_max = max(schema_bytes_max, current_schema_bytes)
                schema_bytes_total += current_schema_bytes
                logger.debug(
                    "Tool schema payload: iteration={}, tools={}, bytes={}, est_tokens={}",
                    iteration,
                    schema_tool_count_last,
                    current_schema_bytes,
                    self._estimate_token_count(current_schema_bytes),
                )

            try:
                response = await self.provider.chat(
                    messages=messages,
                    tools=current_tools,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    reasoning_effort=self.reasoning_effort,
                    on_progress=_stream_progress,
                    source="main",
                )
            finally:
                for _m in messages:
                    _m.pop("_image", None)

            logger.debug(
                "LLM response: model={}, has_tool_calls={}, tool_count={}, finish_reason={}",
                self.model,
                response.has_tool_calls,
                len(response.tool_calls),
                response.finish_reason,
            )

            if response.finish_reason == "interrupted":
                interrupted = True
                break

            if response.has_tool_calls:
                _iter_completed: list[dict[str, Any]] = []
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
                    thinking_blocks=response.thinking_blocks,
                )
                _iter_completed.append(
                    {
                        "role": "assistant",
                        "content": self._strip_think(response.content) or None,
                        "tool_calls": tool_call_dicts,
                    }
                )

                error_feedback: str | None = None
                if current_task_ref is not None and current_task_ref in self._interrupted_tasks:
                    interrupted = True
                    break
                for tool_call in response.tool_calls:
                    if consecutive_errors > 0:
                        retry_attempts_proxy += 1
                    tools_used.append(tool_call.name)
                    args_preview = shared.summarize_tool_args_for_trace(
                        tool_call.name,
                        tool_call.arguments,
                        max_len=200,
                    )
                    logger.info("🔧 工具调用 / tool: {}({})", tool_call.name, args_preview)
                    tool_task = asyncio.create_task(
                        self.tools.execute(tool_call.name, tool_call.arguments)
                    )
                    raw_result = await self._await_tool_with_interrupt(tool_task, current_task_ref)
                    result_text = raw_result if isinstance(raw_result, str) else str(raw_result)
                    if result_text.startswith("Error: Invalid parameters for tool "):
                        invalid_parameter_errors += 1
                    if result_text.startswith("Error: Tool '") and " not found." in result_text:
                        tool_not_found_errors += 1
                    if result_text.startswith("Error executing "):
                        execution_errors += 1
                    if result_text == self._TOOL_CANCELLED_MSG:
                        interrupted_tool_calls += 1
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
                    if (
                        tool_call.name == "screenshot"
                        and isinstance(result, str)
                        and result.startswith("__SCREENSHOT__:")
                    ):
                        marker = result
                        result = "[screenshot unavailable]"
                        _ss_path = marker[len("__SCREENSHOT__:") :].strip()
                        _ss_file = Path(_ss_path).expanduser()
                        _tmp_dir = Path(tempfile.gettempdir()).resolve()
                        try:
                            _resolved_parent = _ss_file.resolve(strict=False).parent
                        except Exception:
                            _resolved_parent = None
                        _safe_marker = (
                            _ss_file.name.startswith("bao_screenshot_")
                            and _resolved_parent == _tmp_dir
                        )
                        if _safe_marker:
                            try:
                                import base64 as _b64mod

                                with _ss_file.open("rb") as _sf:
                                    _screenshot_image_b64 = _b64mod.b64encode(_sf.read()).decode()
                                result = "[screenshot captured]"
                            except Exception as _ss_err:
                                logger.warning(
                                    "⚠️ 截图读取失败 / screenshot read failed: {}: {}",
                                    _ss_file,
                                    _ss_err,
                                )
                            finally:
                                try:
                                    if _ss_file.exists():
                                        _ss_file.unlink()
                                except Exception:
                                    pass
                        else:
                            logger.warning(
                                "⚠️ 忽略非安全截图路径 / ignored unsafe screenshot path: {}",
                                _ss_file,
                            )
                    messages = self.context.add_tool_result(
                        messages,
                        tool_call.id,
                        tool_call.name,
                        result,
                        image_base64=_screenshot_image_b64,
                    )
                    _iter_completed.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.name,
                            "content": result,
                        }
                    )

                    has_error = shared.has_tool_error(
                        tool_call.name,
                        result_text,
                        _ERROR_KEYWORDS,
                    )

                    trace_idx = len(tool_trace) + 1
                    trace_entry = shared.build_tool_trace_entry(
                        trace_idx,
                        tool_call.name,
                        args_preview,
                        has_error,
                        result,
                    )
                    tool_trace.append(trace_entry)
                    sufficiency_trace.append(trace_entry)
                    if len(sufficiency_trace) > 32:
                        del sufficiency_trace[:-32]
                    total_tool_steps_for_sufficiency += 1

                    if has_error:
                        total_errors += 1
                        consecutive_errors += 1
                        failed_preview = shared.summarize_tool_args_for_trace(
                            tool_call.name,
                            tool_call.arguments,
                            max_len=80,
                        )
                        shared.push_failed_direction(
                            failed_directions,
                            f"{tool_call.name}({failed_preview})",
                        )
                    else:
                        consecutive_errors = 0
                        tool_calls_ok += 1

                    # Interrupt: yield to pending user message at tool boundary
                    if current_task_ref is not None and current_task_ref in self._interrupted_tasks:
                        if _iter_completed:
                            _completed_tool_msgs.extend(_iter_completed)
                        logger.debug(
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
                if _iter_completed and not interrupted:
                    _completed_tool_msgs.extend(_iter_completed)
                # Break outer loop if interrupted at tool boundary
                if current_task_ref is not None and current_task_ref in self._interrupted_tasks:
                    interrupted = True
                    break
            else:
                if current_task_ref is not None and current_task_ref in self._interrupted_tasks:
                    interrupted = True
                    break
                clean_final = self._strip_think(response.content)
                if response.finish_reason == "error":
                    logger.error("LLM returned error: {}", (clean_final or "")[:200])
                    safe_error = (
                        clean_final or "Sorry, I encountered an error calling the AI model."
                    )
                    final_content = safe_error
                    provider_error = True
                    break
                if force_final_response and not force_final_backoff_used and not clean_final:
                    force_final_response = False
                    force_final_backoff_used = True
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your previous final response was empty. "
                                "If more evidence is needed, use tools briefly and then provide a complete final answer."
                            ),
                        }
                    )
                    continue
                final_content = clean_final
                messages = self.context.add_assistant_message(
                    messages,
                    clean_final,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
                break

        self._last_tool_budget = tool_budget
        total_tool_calls = len(tools_used)
        tool_calls_error = max(0, total_tool_calls - tool_calls_ok)
        parameter_fill_success = max(0, total_tool_calls - invalid_parameter_errors)
        schema_bytes_avg = schema_bytes_total // schema_samples if schema_samples > 0 else 0
        self._last_tool_observability = {
            "schema_samples": schema_samples,
            "schema_tool_count_last": schema_tool_count_last,
            "schema_tool_count_max": schema_tool_count_max,
            "schema_bytes_last": schema_bytes_last,
            "schema_bytes_max": schema_bytes_max,
            "schema_bytes_avg": schema_bytes_avg,
            "schema_tokens_est_last": self._estimate_token_count(schema_bytes_last),
            "tool_calls_total": total_tool_calls,
            "tool_calls_ok": tool_calls_ok,
            "tool_calls_error": tool_calls_error,
            "invalid_parameter_errors": invalid_parameter_errors,
            "tool_not_found_errors": tool_not_found_errors,
            "execution_errors": execution_errors,
            "interrupted_tool_calls": interrupted_tool_calls,
            "retry_attempts_proxy": retry_attempts_proxy,
            "post_error_tool_calls_proxy": retry_attempts_proxy,
            "total_errors": total_errors,
            "tool_selection_hit_rate": self._safe_rate(tool_calls_ok, total_tool_calls),
            "parameter_fill_success_rate": self._safe_rate(
                parameter_fill_success,
                total_tool_calls,
            ),
            "retry_rate_proxy": self._safe_rate(retry_attempts_proxy, total_tool_calls),
        }
        logger.debug("Tool observability summary: {}", self._last_tool_observability)
        if return_interrupt:
            return (
                final_content,
                tools_used,
                tool_trace,
                total_errors,
                reasoning_snippets,
                provider_error,
                interrupted,
                _completed_tool_msgs,
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
                natural_key = self._dispatch_session_key(msg)
                active_key = self.sessions.get_active_session_key(natural_key)
                target_keys = [natural_key]
                if active_key and active_key != natural_key:
                    target_keys.append(active_key)
                for target_key in target_keys:
                    session = self.sessions.get_or_create(target_key)
                    if self._clear_interactive_state(session):
                        self.sessions.save(session)
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
                        self._interrupted_tasks.add(t)

                    running_task = self._session_running_task.get(session_key)
                    if running_task and not running_task.done():
                        self._interrupted_tasks.add(running_task)

                    cmd = (msg.content or "").strip().lower()
                    if msg.channel != "system" and not cmd.startswith("/"):
                        natural_key = msg.session_key
                        active_override = self.sessions.get_active_session_key(natural_key)
                        key = active_override or natural_key
                        session = self.sessions.get_or_create(key)
                        pre_saved_token = msg.metadata.get("_pre_saved_token")
                        if not isinstance(pre_saved_token, str) or not pre_saved_token:
                            pre_saved_token = uuid.uuid4().hex
                            msg.metadata["_pre_saved_token"] = pre_saved_token
                        session.add_message(
                            "user",
                            msg.content,
                            _pre_saved=True,
                            _pre_saved_token=pre_saved_token,
                        )
                        self.sessions.save(session)
                        msg.metadata["_pre_saved"] = True

                    if getattr(self.provider, "_api_mode", None) == "responses":
                        for t in busy_tasks:
                            if not t.done():
                                t.cancel()

                    logger.debug("Soft interrupt requested for busy session {}", session_key)

                task_gen = self._session_generations.get(session_key, 0)
                task = asyncio.create_task(
                    self._dispatch(msg, task_generation=task_gen, dispatch_key=session_key)
                )
                self._active_tasks.setdefault(session_key, []).append(task)
                self._session_locks.setdefault(session_key, asyncio.Lock())

                def _on_done(t: asyncio.Task[None], k: str = session_key) -> None:
                    task_list = self._active_tasks.get(k)
                    if not task_list:
                        self._interrupted_tasks.discard(t)
                        return
                    try:
                        task_list.remove(t)
                    except ValueError:
                        self._interrupted_tasks.discard(t)
                        return
                    self._interrupted_tasks.discard(t)
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
                self._interrupted_tasks.discard(running_task)

            tasks = self._active_tasks.get(target_key, [])
            for t in tasks:
                self._interrupted_tasks.discard(t)
            cancelled += sum(1 for t in tasks if not t.done() and t.cancel())
            if not any(not t.done() for t in tasks):
                self._active_tasks.pop(target_key, None)
                self._session_locks.pop(target_key, None)

            sub_cancelled += await cast(Any, self.subagents).cancel_by_session(
                target_key, wait=False
            )

        total = cancelled + sub_cancelled
        content = f"\u23f9 Stopped {total} task(s)." if total else "No active task to stop."
        out_meta = dict(msg.metadata or {})
        reply_to = out_meta.get("reply_to") if isinstance(out_meta.get("reply_to"), str) else None
        await self.bus.publish_outbound(
            OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=content,
                reply_to=reply_to,
                metadata=out_meta,
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
                        logger.debug(
                            "Dropping stale response for session {} after /stop", dispatch_key
                        )
                        return
                    # Notify callback for system messages (subagent completion)
                    if msg.channel == "system" and self.on_system_response:
                        try:
                            await self.on_system_response(response)
                        except Exception as cb_err:
                            logger.debug("on_system_response callback failed: {}", cb_err)
                    await self.bus.publish_outbound(response)
            except asyncio.CancelledError:
                logger.debug("Task cancelled for session {}", dispatch_key)
                raise
            except Exception as e:
                logger.error("❌ 消息处理失败 / message error: {}", e)
                if self._session_generations.get(dispatch_key, 0) != task_generation:
                    logger.debug("Suppressing stale error response for session {}", dispatch_key)
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
                    self._interrupted_tasks.discard(current_task)
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
        logger.info("👋 停止代理 / agent stopping: main loop")

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
        logger.info("📨 收到消息 / in: {}:{}: {}", msg.channel, msg.sender_id, preview)

        # Layer 1/2: one-time stale artifact cleanup per process lifetime
        if not self._artifact_cleanup_done:
            self._artifact_cleanup_done = True
            try:
                from bao.agent.artifacts import ArtifactStore

                ArtifactStore(
                    self.workspace, "_stale_", self._artifact_retention_days
                ).cleanup_stale()
            except Exception as _e:
                logger.debug("ctx stale cleanup failed: {}", _e)
        natural_key = session_key or msg.session_key
        active_override = self.sessions.get_active_session_key(natural_key)
        key = active_override or natural_key
        session = self.sessions.get_or_create(key)

        # Handle slash commands
        cmd = msg.content.strip().lower()
        if cmd.startswith("/") and self._clear_interactive_state(session):
            self.sessions.save(session)
        if cmd == "/new":
            if session.messages:
                old_messages = session.messages.copy()
                old_key = session.key
                old_metadata = dict(session.metadata)
                old_last_consolidated = session.last_consolidated
                old_created_at = session.created_at
                old_updated_at = session.updated_at
                archive_sig = _archive_all_signature(old_messages)
                last_archive_sig = str(session.metadata.get("_last_archive_all_sig", ""))

                async def _consolidate_old():
                    temp = Session(
                        key=old_key,
                        messages=old_messages,
                        metadata=old_metadata,
                        last_consolidated=old_last_consolidated,
                        created_at=old_created_at,
                        updated_at=old_updated_at,
                    )
                    await self._consolidate_memory(temp, archive_all=True)

                if archive_sig and archive_sig != last_archive_sig:
                    session.metadata["_last_archive_all_sig"] = archive_sig
                    self.sessions.save(session)
                    asyncio.create_task(_consolidate_old())
            idx = len(self.sessions.list_sessions_for(natural_key)) + 1
            name = f"s{idx}"
            while self.sessions.session_exists(f"{natural_key}::{name}"):
                idx += 1
                name = f"s{idx}"
            commands.create_and_switch(self.sessions, natural_key, name)
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
            return commands.handle_model_command(
                cmd,
                msg,
                session,
                available_models=self.available_models,
                current_model=self.model,
                sessions=self.sessions,
                apply_fn=self._apply_model_switch,
            )

        if cmd == "/session":
            return commands.handle_session_command(msg, natural_key, sessions=self.sessions)

        if cmd == "/memory":
            return await self._handle_memory_command(msg, session)

        pending = session.metadata.pop("_pending_model_select", None)
        pending_session = session.metadata.pop("_pending_session_select", None)
        if pending and cmd.isdigit():
            return commands.switch_model(
                int(cmd),
                msg,
                session,
                available_models=self.available_models,
                current_model=self.model,
                sessions=self.sessions,
                apply_fn=self._apply_model_switch,
            )
        if pending_session and cmd.isdigit():
            self.sessions.save(session)
            return commands.select_session(
                int(cmd),
                msg,
                natural_key,
                sessions=self.sessions,
            )

        if (
            session.metadata.get("_pending_memory_list")
            or session.metadata.get("_pending_memory_detail")
            or session.metadata.get("_pending_memory_delete")
            or session.metadata.get("_pending_memory_edit")
        ):
            return await self._handle_memory_input(msg, session)

        # ── File-driven onboarding state machine ──
        # Stage detection: no INSTRUCTIONS.md → lang_select
        #                 no PERSONA.md     → persona_setup
        #                 both exist        → ready
        from bao.config.onboarding import (
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
                from bao.config.onboarding import write_heartbeat, write_instructions

                lang = "zh" if cmd == "1" else "en"
                try:
                    write_instructions(self.workspace, lang)
                except Exception as e:
                    logger.debug("Failed to write instructions template: {}", e)
                try:
                    write_heartbeat(self.workspace, lang)
                except Exception as e:
                    logger.debug("Failed to write heartbeat template: {}", e)
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
                from bao.config.onboarding import write_persona_profile

                try:
                    write_persona_profile(self.workspace, lang, profile)
                    self.context = ContextBuilder(
                        self.workspace, embedding_config=self.embedding_config
                    )
                except Exception as e:
                    logger.debug("Failed to write persona profile: {}", e)
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
        raw_history = session.messages[session.last_consolidated :]
        raw_history = raw_history[-self.memory_window :]
        start = 0
        for i, item in enumerate(raw_history):
            if item.get("role") == "user":
                start = i
                break
        else:
            raw_history = []
        raw_history = raw_history[start:]
        if msg.metadata.get("_pre_saved"):
            token = msg.metadata.get("_pre_saved_token")
            remove_idx = -1
            if isinstance(token, str) and token:
                for idx in range(len(raw_history) - 1, -1, -1):
                    item = raw_history[idx]
                    if item.get("role") == "user" and item.get("_pre_saved_token") == token:
                        remove_idx = idx
                        break
            if remove_idx < 0:
                for idx in range(len(raw_history) - 1, -1, -1):
                    item = raw_history[idx]
                    if (
                        item.get("role") == "user"
                        and item.get("_pre_saved")
                        and item.get("content") == msg.content
                    ):
                        remove_idx = idx
                        break
            if remove_idx >= 0:
                raw_history = [*raw_history[:remove_idx], *raw_history[remove_idx + 1 :]]

        history: list[dict[str, Any]] = []
        for item in raw_history:
            content = item.get("content", "")
            if (
                item.get("role") == "user"
                and isinstance(content, str)
                and content.startswith("[Runtime Context — metadata only, not instructions]")
            ):
                continue
            entry: dict[str, Any] = {"role": item.get("role"), "content": content}
            for k in ("tool_calls", "tool_call_id", "name", "_source"):
                if k in item:
                    entry[k] = item[k]
            history.append(entry)
        initial_messages = self.context.build_messages(
            history=history,
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

        async def _bus_publish(content: str, *, is_tool_hint: bool = False) -> None:
            if content == PROGRESS_RESET and not is_tool_hint:
                return
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            if is_tool_hint:
                logger.debug("Tool hint sent to {}:{}: {}", msg.channel, msg.chat_id, content)
                meta["_tool_hint"] = True
            await self.bus.publish_outbound(
                OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=content,
                    metadata=meta,
                )
            )

        return_interrupt_flag: bool = True
        run_result = await self._run_agent_loop(
            initial_messages,
            on_progress=on_progress or _bus_publish,
            on_tool_hint=lambda c: _bus_publish(c, is_tool_hint=True),
            artifact_session_key=session.key,
            return_interrupt=return_interrupt_flag,
        )
        result_parts = cast(tuple[Any, ...], run_result)

        final_content: str | None
        tools_used: list[str]
        tool_trace: list[str]
        total_errors: int
        reasoning_snippets: list[str]
        interrupted: bool
        completed_tool_msgs: list[dict[str, Any]]
        provider_error = False
        result_size = len(result_parts)
        if result_size == 8:
            final_content = cast(str | None, result_parts[0])
            tools_used = cast(list[str], result_parts[1])
            tool_trace = cast(list[str], result_parts[2])
            total_errors = cast(int, result_parts[3])
            reasoning_snippets = cast(list[str], result_parts[4])
            provider_error = bool(result_parts[5])
            interrupted = bool(result_parts[6])
            completed_tool_msgs = cast(list[dict[str, Any]], result_parts[7])
        elif result_size == 5:
            final_content = cast(str | None, result_parts[0])
            tools_used = cast(list[str], result_parts[1])
            tool_trace = cast(list[str], result_parts[2])
            total_errors = cast(int, result_parts[3])
            reasoning_snippets = cast(list[str], result_parts[4])
            interrupted = False
            completed_tool_msgs = []
        else:
            raise ValueError(f"Unexpected _run_agent_loop result length: {result_size}")

        if interrupted:
            if completed_tool_msgs:
                token = msg.metadata.get("_pre_saved_token")
                insert_after = -1
                if token:
                    for idx, item in enumerate(session.messages):
                        if item.get("role") == "user" and item.get("_pre_saved_token") == token:
                            insert_after = idx
                            break
                if insert_after < 0 and msg.metadata.get("_pre_saved"):
                    for idx in range(len(session.messages) - 1, -1, -1):
                        item = session.messages[idx]
                        if (
                            item.get("role") == "user"
                            and item.get("_pre_saved")
                            and item.get("content") == msg.content
                        ):
                            insert_after = idx
                            break
                if insert_after < 0 and not msg.metadata.get("_pre_saved"):
                    for idx in range(len(session.messages) - 1, -1, -1):
                        item = session.messages[idx]
                        if (
                            item.get("role") == "user"
                            and not item.get("_pre_saved")
                            and item.get("content") == msg.content
                        ):
                            insert_after = idx
                            break
                if insert_after < 0:
                    insert_at = len(session.messages)
                    logger.warning(
                        "Interrupted tool messages had no matching user turn; appending to end for session {}",
                        msg.session_key,
                    )
                else:
                    insert_at = insert_after + 1
                for offset, item in enumerate(completed_tool_msgs):
                    msg_item = dict(item)
                    msg_item.setdefault("timestamp", datetime.now().isoformat())
                    session.messages.insert(insert_at + offset, msg_item)
                session.updated_at = datetime.now()
                self.sessions.save(session)
            logger.debug("Interrupted response dropped for session {}", msg.session_key)
            return None

        generation_key = expected_generation_key or msg.session_key
        if (
            expected_generation is not None
            and self._session_generations.get(generation_key, 0) != expected_generation
        ):
            logger.debug(
                "Suppressing stale completion before persistence for session {}", generation_key
            )
            return None

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        skip_persist_assistant = provider_error

        if (
            expected_generation is not None
            and self._session_generations.get(generation_key, 0) != expected_generation
        ):
            logger.debug(
                "Suppressing stale side-effects before persistence for session {}", generation_key
            )
            return None

        self._maybe_learn_experience(
            session=session,
            user_request=msg.content,
            final_response=final_content,
            tools_used=tools_used,
            tool_trace=tool_trace,
            total_errors=total_errors,
            reasoning_snippets=reasoning_snippets,
        )
        self._persist_tool_observability(session, channel=msg.channel, session_key=key)

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info("💬 回复消息 / out: {}:{}: {}", msg.channel, msg.sender_id, preview)

        persisted_content = final_content
        if (t := self.tools.get("message")) and isinstance(t, MessageTool) and t._sent_in_turn:
            persisted_content = t.last_sent_summary or final_content
        if not skip_persist_assistant and (persisted_content or tools_used):
            session.add_message(
                "assistant", persisted_content, tools_used=tools_used if tools_used else None
            )
        elif skip_persist_assistant:
            logger.debug("Skip persisting provider error response for session {}", key)

        self.sessions.save(session)

        user_turns = sum(1 for m in session.messages if m["role"] == "user")
        if (
            not session.metadata.get("title")
            and user_turns <= 6
            and session.key not in self._title_generation_inflight
        ):
            self._title_generation_inflight.add(session.key)

            async def _generate_and_clear_title() -> None:
                try:
                    await self._generate_session_title(session)
                finally:
                    self._title_generation_inflight.discard(session.key)

            asyncio.create_task(_generate_and_clear_title())

        if (t := self.tools.get("message")) and isinstance(t, MessageTool) and t._sent_in_turn:
            return None

        out_meta = dict(msg.metadata or {})
        reply_to = out_meta.get("reply_to") if isinstance(out_meta.get("reply_to"), str) else None
        if any(self._last_tool_budget.values()):
            out_meta["_tool_budget"] = dict(self._last_tool_budget)
        if self._last_tool_observability:
            out_meta["_tool_observability"] = dict(self._last_tool_observability)

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            reply_to=reply_to,
            metadata=out_meta,
        )

    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        logger.info("📨 收到系统 / system in: {}", msg.sender_id)

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
        return_interrupt_flag: bool = True
        run_result = await self._run_agent_loop(
            initial_messages,
            artifact_session_key=session.key,
            return_interrupt=return_interrupt_flag,
        )
        result_parts = cast(tuple[Any, ...], run_result)

        provider_error = False
        if len(result_parts) == 8:
            final_content = cast(str | None, result_parts[0])
            tools_used = cast(list[str], result_parts[1])
            tool_trace = cast(list[str], result_parts[2])
            total_errors = cast(int, result_parts[3])
            reasoning_snippets = cast(list[str], result_parts[4])
            provider_error = bool(result_parts[5])
        elif len(result_parts) == 5:
            final_content = cast(str | None, result_parts[0])
            tools_used = cast(list[str], result_parts[1])
            tool_trace = cast(list[str], result_parts[2])
            total_errors = cast(int, result_parts[3])
            reasoning_snippets = cast(list[str], result_parts[4])
        else:
            raise ValueError(f"Unexpected _run_agent_loop result length: {len(result_parts)}")

        if final_content is None:
            final_content = "Background task completed."

        skip_persist_assistant = provider_error

        self._maybe_learn_experience(
            session=session,
            user_request=msg.content,
            final_response=final_content,
            tools_used=tools_used,
            tool_trace=tool_trace,
            total_errors=total_errors,
            reasoning_snippets=reasoning_snippets,
        )
        self._persist_tool_observability(
            session,
            channel=origin_channel,
            session_key=session_key,
        )

        session.add_message(
            "user", f"[System: {msg.sender_id}] {msg.content}", _source=msg.sender_id
        )
        persisted_content = final_content
        if (t := self.tools.get("message")) and isinstance(t, MessageTool) and t._sent_in_turn:
            persisted_content = t.last_sent_summary or final_content
        if not skip_persist_assistant and (persisted_content or tools_used):
            session.add_message(
                "assistant", persisted_content, tools_used=tools_used if tools_used else None
            )
        elif skip_persist_assistant:
            logger.debug(
                "Skip persisting provider error response for system session {}", session_key
            )
        self.sessions.save(session)

        # If message tool already sent content, suppress duplicate outbound
        if (t := self.tools.get("message")) and isinstance(t, MessageTool) and t._sent_in_turn:
            return None

        out_meta: dict[str, Any] = dict(msg.metadata or {})
        out_meta["session_key"] = session_key
        reply_to = out_meta.get("reply_to") if isinstance(out_meta.get("reply_to"), str) else None
        if any(self._last_tool_budget.values()):
            out_meta["_tool_budget"] = dict(self._last_tool_budget)
        if self._last_tool_observability:
            out_meta["_tool_observability"] = dict(self._last_tool_observability)

        return OutboundMessage(
            channel=origin_channel,
            chat_id=origin_chat_id,
            content=final_content,
            reply_to=reply_to,
            metadata=out_meta,
        )

    @staticmethod
    def _reply(msg: "InboundMessage", content: str) -> "OutboundMessage":
        return commands.reply(msg, content)

    def _apply_model_switch(self, new_model: str) -> None:
        old_provider = self.provider
        old_model = self.model

        try:
            if not self._config:
                self.model = new_model
                self.subagents.model = new_model
                return

            from bao.providers import make_provider

            new_provider = make_provider(self._config, new_model)
            self.provider = new_provider
            self.subagents.provider = new_provider
            self.subagents.model = new_model
            self.model = new_model
        except Exception as e:
            self.provider = old_provider
            self.subagents.provider = old_provider
            self.subagents.model = old_model
            self.model = old_model
            logger.warning("⚠️ Provider 重建失败 / rebuild failed for {}: {}", new_model, e)
            raise

    def _clear_memory_state(self, session: Session) -> None:
        for k in (
            "_pending_memory_list",
            "_pending_memory_detail",
            "_pending_memory_delete",
            "_pending_memory_edit",
            "_memory_entries",
            "_memory_selected_index",
        ):
            session.metadata.pop(k, None)

    def _clear_model_session_state(self, session: Session) -> None:
        session.metadata.pop("_pending_model_select", None)
        session.metadata.pop("_pending_session_select", None)

    def _clear_interactive_state(self, session: Session) -> bool:
        keys = (
            "_pending_memory_list",
            "_pending_memory_detail",
            "_pending_memory_delete",
            "_pending_memory_edit",
            "_memory_entries",
            "_memory_selected_index",
            "_pending_model_select",
            "_pending_session_select",
        )
        if not any(k in session.metadata for k in keys):
            return False
        self._clear_memory_state(session)
        self._clear_model_session_state(session)
        return True

    async def _handle_memory_command(
        self, msg: InboundMessage, session: Session
    ) -> OutboundMessage:
        entries = await asyncio.to_thread(self.context.memory.list_long_term_entries)
        if not entries:
            self._clear_memory_state(session)
            self.sessions.save(session)
            return self._reply(msg, "暂无记忆 📭")

        self._clear_memory_state(session)

        by_cat: dict[str, list[tuple[int, dict[str, str]]]] = {}
        for i, e in enumerate(entries, 1):
            cat = e.get("category", "general")
            by_cat.setdefault(cat, []).append((i, e))

        lines = ["🧠 记忆列表:\n"]
        for cat, items in by_cat.items():
            lines.append(f"[{cat}]")
            for idx, e in items:
                content = e.get("content", "")
                preview = content[:60].replace("\n", " ")
                if len(content) > 60:
                    preview += "..."
                lines.append(f"  {idx}. {preview}")
            lines.append("")

        lines.append("输入编号查看详情，输入 0 进入删除模式，其他输入退出")

        session.metadata["_pending_memory_list"] = True
        session.metadata["_memory_entries"] = entries
        self.sessions.save(session)

        return self._reply(msg, "\n".join(lines))

    async def _handle_memory_input(self, msg: InboundMessage, session: Session) -> OutboundMessage:
        text = msg.content.strip()
        entries: list[dict[str, str]] = session.metadata.get("_memory_entries", [])

        if session.metadata.get("_pending_memory_edit"):
            idx = session.metadata.get("_memory_selected_index", 0)
            if 0 < idx <= len(entries):
                entry = entries[idx - 1]
                cat = entry.get("category", "general")
                key = entry.get("key", "")
                key_exists = await asyncio.to_thread(self.context.memory.exists_long_term_key, key)
                if not key or not key_exists:
                    self._clear_memory_state(session)
                    self.sessions.save(session)
                    return self._reply(msg, "该记忆已失效，请重新 /memory")
                if not text:
                    self._clear_memory_state(session)
                    self.sessions.save(session)
                    return self._reply(msg, "内容为空，已取消编辑")
                deleted_by_key = await asyncio.to_thread(
                    self.context.memory.delete_long_term_by_key, key
                )
                if not deleted_by_key:
                    self._clear_memory_state(session)
                    self.sessions.save(session)
                    return self._reply(msg, "该记忆已失效，请重新 /memory")
                await asyncio.to_thread(self.context.memory.write_long_term, text, cat)
                self._clear_memory_state(session)
                self.sessions.save(session)
                return self._reply(msg, f"已更新 [{cat}] 记忆 ✅")
            self._clear_memory_state(session)
            self.sessions.save(session)
            return self._reply(msg, "无效操作，已退出记忆管理")

        if session.metadata.get("_pending_memory_delete"):
            fresh = await asyncio.to_thread(self.context.memory.list_long_term_entries)
            fresh_keys = {e.get("key", "") for e in fresh}
            parts = set(text.split())
            deleted = 0
            skipped = 0
            for p in parts:
                if p.isdigit():
                    idx = int(p)
                    if 0 < idx <= len(entries):
                        key = entries[idx - 1].get("key", "")
                        if key and key not in fresh_keys:
                            skipped += 1
                            continue
                        if key:
                            deleted_by_key = await asyncio.to_thread(
                                self.context.memory.delete_long_term_by_key, key
                            )
                            if deleted_by_key:
                                deleted += 1
                                fresh_keys.discard(key)
            if deleted:
                asyncio.create_task(
                    asyncio.to_thread(self.context.memory.embed_long_term_aggregate)
                )
            self._clear_memory_state(session)
            self.sessions.save(session)
            if deleted:
                suffix = f"（{skipped} 条已失效跳过）" if skipped else ""
                return self._reply(msg, f"已删除 {deleted} 条记忆 🗑️{suffix}")
            if skipped:
                return self._reply(msg, f"{skipped} 条记忆已失效，未执行删除")
            return self._reply(msg, "未删除任何记忆，已退出")

        if session.metadata.get("_pending_memory_detail"):
            if text == "9":
                session.metadata["_pending_memory_edit"] = True
                session.metadata.pop("_pending_memory_detail", None)
                self.sessions.save(session)
                return self._reply(msg, "请输入新内容替换该条记忆：")
            if text == "0":
                idx = session.metadata.get("_memory_selected_index", 0)
                deleted = False
                if 0 < idx <= len(entries):
                    key = entries[idx - 1].get("key", "")
                    if key:
                        fresh = await asyncio.to_thread(self.context.memory.list_long_term_entries)
                        fresh_keys = {e.get("key", "") for e in fresh}
                        if key not in fresh_keys:
                            self._clear_memory_state(session)
                            self.sessions.save(session)
                            return self._reply(msg, "该记忆已失效，无需删除")
                        deleted = await asyncio.to_thread(
                            self.context.memory.delete_long_term_by_key, key
                        )
                        if deleted:
                            asyncio.create_task(
                                asyncio.to_thread(self.context.memory.embed_long_term_aggregate)
                            )
                self._clear_memory_state(session)
                self.sessions.save(session)
                if deleted:
                    return self._reply(msg, "已删除该条记忆 🗑️")
                return self._reply(msg, "删除失败")
            return await self._handle_memory_command(msg, session)

        if session.metadata.get("_pending_memory_list"):
            if text == "0":
                session.metadata["_pending_memory_delete"] = True
                session.metadata.pop("_pending_memory_list", None)
                self.sessions.save(session)
                return self._reply(msg, "输入要删除的编号（空格分隔可批量删），输入其他退出")
            if text.isdigit():
                idx = int(text)
                if 0 < idx <= len(entries):
                    entry = entries[idx - 1]
                    cat = entry.get("category", "general")
                    content = entry.get("content", "")
                    session.metadata["_pending_memory_detail"] = True
                    session.metadata["_memory_selected_index"] = idx
                    session.metadata.pop("_pending_memory_list", None)
                    self.sessions.save(session)
                    return self._reply(
                        msg,
                        f"🧠 [{cat}] 记忆详情:\n\n{content}\n\n输入 9 编辑，输入 0 删除，其他返回列表",
                    )
                self._clear_memory_state(session)
                self.sessions.save(session)
                return self._reply(msg, "无效编号，已退出记忆管理")
            self._clear_memory_state(session)
            self.sessions.save(session)
            return self._reply(msg, "已退出记忆管理 👌")

        self._clear_memory_state(session)
        self.sessions.save(session)
        return self._reply(msg, "已退出记忆管理 👌")

    async def _consolidate_memory(self, session, archive_all: bool = False) -> None:
        memory = self.context.memory
        target_last_consolidated = session.last_consolidated

        if archive_all:
            old_messages = session.messages
            keep_count = 0
            logger.info(
                "🧠 开始整合 / consolidation start: {} total messages archived",
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

            snapshot_total = len(session.messages)
            snapshot_stop = max(session.last_consolidated, snapshot_total - keep_count)
            old_messages = session.messages[session.last_consolidated : snapshot_stop]
            if not old_messages:
                return
            target_last_consolidated = snapshot_stop
            logger.info(
                "🧠 开始整合 / consolidation start: {} total, {} new to consolidate, {} keep",
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
        current_memory_parts: list[str] = []
        for category in MEMORY_CATEGORIES:
            category_memory = memory.read_long_term(category).strip()
            current_memory_parts.append(f"### {category}\n{category_memory or '(empty)'}")
        current_memory = "\n\n".join(current_memory_parts)

        caps_text = "\n".join(
            f'   - "{cat}": <= {MEMORY_CATEGORY_CAPS[cat]} chars' for cat in MEMORY_CATEGORIES
        )

        prompt = f"""You are a memory consolidation agent. Process this conversation and return a JSON object with exactly two keys:

1. "history_entry": A paragraph (2-5 sentences) summarizing key events/decisions/topics. Start with a timestamp like [YYYY-MM-DD HH:MM].

2. "memory_updates": An object where keys are memory categories and values are the FINAL merged content for that category.

Memory categories:
   - "preference": User preferences, habits, communication style, likes/dislikes
   - "personal": User identity, location, relationships, personal facts
   - "project": Project context, technical decisions, tools/services, codebase info
   - "general": Other durable facts that don't fit above categories

Hard caps per category:
{caps_text}

Rules for memory_updates:
   - Merge with existing memory; do not blindly append duplicates.
   - Keep only durable facts. Remove stale or contradictory items.
   - Values must contain ONLY category content. Do NOT include headings like "### preference" or markers like "[preference]".
   - You may set a category to "" to intentionally clear it.
   - ONLY memorize facts that are likely useful across multiple future sessions.
   - DO NOT memorize: transient chat content, debugging details, one-off commands, temporary file paths, or emotional reactions.
   - DO NOT memorize anything already covered by PERSONA.md (name, role, location, language — these are static profile).
   - If a fact is already present in existing memory with equivalent meaning, do NOT add a rephrased duplicate.
   - When in doubt, prefer NOT writing over writing — false negatives are cheaper than noise.

## Current Long-term Memory (by category)
{current_memory}

## Conversation to Process
{conversation}

Respond with ONLY valid JSON, no markdown fences."""

        try:
            provider = self._utility_provider or self.provider
            model = self._utility_model or self.model
            response = await asyncio.wait_for(
                provider.chat(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a memory consolidation agent. Respond only with valid JSON.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    model=model,
                    source="utility",
                ),
                timeout=90,
            )
            text = (response.content or "").strip()
            if not text:
                logger.warning("⚠️ 整合结果为空 / empty response: memory consolidation skipped")
                return
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json_repair.loads(text)
            if not isinstance(result, dict):
                logger.warning(
                    "⚠️ 整合返回异常 / unexpected response: {}",
                    text[:200],
                )
                return

            if entry := result.get("history_entry"):
                if not isinstance(entry, str):
                    entry = json.dumps(entry, ensure_ascii=False)
                await asyncio.to_thread(memory.append_history, entry)
            # Handle categorized memory updates (new) or single update (legacy)
            if updates := result.get("memory_updates"):
                if isinstance(updates, dict):
                    await asyncio.to_thread(memory.write_categorized_memory, updates)
            elif update := result.get("memory_update"):
                if not isinstance(update, str):
                    update = json.dumps(update, ensure_ascii=False)
                if update != current_memory:
                    await asyncio.to_thread(memory.write_long_term, update)

            if archive_all:
                pass
            else:
                session.last_consolidated = target_last_consolidated
                self.sessions.save(session)
            logger.info(
                "✅ 完成整合 / consolidation done: {} messages, last_consolidated={}",
                len(session.messages),
                session.last_consolidated,
            )
        except Exception as e:
            logger.error("❌ 记忆整合失败 / consolidation failed: {}", e)

    @staticmethod
    def _parse_llm_json(content: str | None) -> dict[str, Any] | None:
        return shared.parse_llm_json(content)

    async def _call_utility_llm(self, system: str, prompt: str) -> dict[str, Any] | None:
        if self._utility_provider is not None and self._utility_model:
            provider = self._utility_provider
            model = self._utility_model
        else:
            provider = self.provider
            model = self.model
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
        # Find first non-greeting user message + its paired assistant reply
        user_msg = None
        user_idx = -1
        for i, m in enumerate(session.messages):
            if m["role"] == "user":
                text = (
                    _extract_text(m.get("content", ""))
                    .strip()
                    .strip("!\uff01?\uff1f.\u3002~\uff5e")
                    .lower()
                )
                if text and text not in _GREETING_WORDS and len(text) >= 2:
                    user_msg = m
                    user_idx = i
                    break
        if not user_msg:
            return
        # Pick the assistant reply that follows the selected user message
        assistant_msg = None
        for m in session.messages[user_idx + 1 :]:
            if m["role"] == "assistant" and _extract_text(m.get("content", "")):
                assistant_msg = m
                break
        if not assistant_msg:
            return

        user_content = _extract_text(user_msg["content"])[:500]
        assistant_content = _extract_text(assistant_msg["content"])[:300]

        prompt = (
            "Generate a short conversation title. Rules:\n"
            "- Chinese: max 12 chars. English: max 6 words\n"
            "- No quotes, no periods, no prefixes like '\u5173\u4e8e...'\n"
            "- Match the user's language\n\n"
            f"User: {user_content}\n"
            f"Assistant: {assistant_content}\n\n"
            'Return JSON: {"title": "your title here"}'
        )

        fallback_text = _extract_text(user_msg["content"]).strip()[:20]
        try:
            result = await self._call_utility_llm(
                "You are a conversation title generator. Respond only with valid JSON.",
                prompt,
            )
            title = (
                str(result.get("title", ""))
                .strip()
                .strip("\"''\u201c\u201d\u2018\u2019\u3002.!\uff01")
                if result
                else ""
            )
            if title and not session.metadata.get("title"):
                session.metadata["title"] = title[:30]
                self.sessions.save(session)
                logger.debug("Session title generated: {} \u2192 {}", session.key, title[:30])
                return
        except Exception as e:
            logger.debug("Session title generation failed: {}", e)
        # Fallback: use first user message text
        try:
            if fallback_text and not session.metadata.get("title"):
                session.metadata["title"] = fallback_text
                self.sessions.save(session)
        except Exception:
            pass

    async def _call_experience_llm(self, system: str, prompt: str) -> dict[str, Any] | None:
        return await shared.call_experience_llm(
            system,
            prompt,
            experience_mode=self._experience_mode,
            provider=self.provider,
            model=self.model,
            utility_provider=self._utility_provider,
            utility_model=self._utility_model,
        )

    def _compact_messages(
        self,
        messages: list[dict[str, Any]],
        initial_messages: list[dict[str, Any]],
        last_state_text: str | None,
        artifact_store: "ArtifactStore | None",
    ) -> list[dict[str, Any]]:
        return shared.compact_messages(
            messages,
            initial_messages,
            last_state_text,
            artifact_store,
            keep_blocks=self._compact_keep_blocks,
        )

    async def _compress_state(
        self,
        tool_trace: list[str],
        reasoning_snippets: list[str],
        failed_directions: list[str],
        previous_state: str | None = None,
    ) -> str | None:
        return await shared.compress_state(
            tool_trace,
            reasoning_snippets,
            failed_directions,
            previous_state,
            experience_mode=self._experience_mode,
            llm_fn=self._call_experience_llm,
            label="agent",
        )

    async def _check_sufficiency(
        self, user_request: str, tool_trace: list[str], last_state_text: str | None = None
    ) -> bool:
        return await shared.check_sufficiency(
            user_request,
            tool_trace,
            experience_mode=self._experience_mode,
            llm_fn=self._call_experience_llm,
            last_state_text=last_state_text,
        )

    def _maybe_learn_experience(
        self,
        *,
        session: Session,
        user_request: str,
        final_response: str,
        tools_used: list[str],
        tool_trace: list[str],
        total_errors: int,
        reasoning_snippets: list[str] | None,
    ) -> None:
        if self._experience_mode == "none":
            return

        if len(tools_used) >= 3 or total_errors >= 2:
            asyncio.create_task(
                experience.summarize_experience(
                    self.context.memory,
                    self._call_utility_llm,
                    user_request,
                    final_response,
                    tools_used,
                    tool_trace,
                    total_errors,
                    reasoning_snippets,
                )
            )

        if len(session.messages) % 10 == 0:
            asyncio.create_task(
                experience.merge_and_cleanup_experiences(
                    self.context.memory,
                    self._call_utility_llm,
                )
            )

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
