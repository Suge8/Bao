"""Agent loop: the core processing engine."""

import asyncio
from contextlib import AsyncExitStack
import json
import json_repair
from pathlib import Path
import re
from typing import Any, Awaitable, Callable

from loguru import logger

from bao.bus.events import InboundMessage, OutboundMessage
from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider
from bao.agent.context import ContextBuilder
from bao.agent.tools.registry import ToolRegistry
from bao.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from bao.agent.tools.shell import ExecTool
from bao.agent.tools.web import WebSearchTool, WebFetchTool
from bao.agent.tools.message import MessageTool
from bao.agent.tools.spawn import SpawnTool
from bao.agent.tools.cron import CronTool
from bao.agent.memory import MemoryStore
from bao.agent.subagent import SubagentManager
from bao.session.manager import Session, SessionManager


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
        mcp_servers: dict | None = None,
        available_models: list[str] | None = None,
        config: "Config | None" = None,
    ):
        from bao.config.schema import ExecToolConfig
        from bao.cron.service import CronService

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
        )

        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self._consolidating: set[str] = set()  # Session keys with consolidation in progress
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
            config.agents.defaults.experience_model if config else "utility"
        ).lower()

        self._last_progress_content: dict[str, tuple[str, float]] = {}
        self._progress_min_interval = 2.0

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
            )
        )
        search_tool = WebSearchTool(search_config=self.search_config)
        has_brave = bool(search_tool.brave_key)
        has_tavily = bool(search_tool.tavily_key)
        if has_brave or has_tavily:
            providers = [p for p, ok in [("tavily", has_tavily), ("brave", has_brave)] if ok]
            logger.info("web_search enabled ({})", ", ".join(providers))
            self.tools.register(search_tool)
            self.context.tool_hints.append(
                "You have `web_search` — PREFER it over `web_fetch` for finding information, news, or answers. "
                "`web_fetch` is only for reading a specific known URL. Never scrape multiple sites when a single search would suffice."
            )
        else:
            self.context.tool_hints.append(
                "You do NOT have `web_search` (no search API key configured). "
                "Do NOT mention or attempt to use `web_search`. "
                "To search for information, use `web_fetch` to access a search engine URL instead."
            )
        self.tools.register(WebFetchTool())
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(SpawnTool(manager=self.subagents))
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

    async def _connect_mcp(self) -> None:
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from bao.agent.tools.mcp import connect_mcp_servers

        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
            self._mcp_connected = True
        except Exception as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except Exception:
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False

    def _set_tool_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        if (t := self.tools.get("message")) and isinstance(t, MessageTool):
            t.set_context(channel, chat_id, message_id)
        if (t := self.tools.get("spawn")) and isinstance(t, SpawnTool):
            t.set_context(channel, chat_id)
        if (t := self.tools.get("cron")) and isinstance(t, CronTool):
            t.set_context(channel, chat_id)

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    def _should_send_progress(self, channel: str, chat_id: str, content: str) -> bool:
        key = f"{channel}:{chat_id}"
        now = asyncio.get_event_loop().time()

        if key in self._last_progress_content:
            last_content, last_time = self._last_progress_content[key]
            if content == last_content:
                return False
            if now - last_time < self._progress_min_interval:
                return False

        self._last_progress_content[key] = (content, now)
        return True

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        def _fmt(tc):
            val = next(iter(tc.arguments.values()), None) if tc.arguments else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'

        return ", ".join(_fmt(tc) for tc in tool_calls)

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[str], list[str], int, list[str]]:
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []
        tool_trace: list[str] = []
        reasoning_snippets: list[str] = []
        consecutive_errors = 0
        total_errors = 0
        failed_directions: list[str] = []
        last_state_at = 0
        last_state_text: str | None = None
        user_request = next(
            (
                m["content"]
                for m in reversed(initial_messages)
                if m.get("role") == "user" and isinstance(m.get("content"), str)
            ),
            "",
        )

        while iteration < self.max_iterations:
            iteration += 1

            steps_since_state = len(tool_trace) - last_state_at
            if steps_since_state >= 5 and len(tool_trace) >= 5:
                state = await self._compress_state(
                    tool_trace, reasoning_snippets, failed_directions, last_state_text
                )
                if state:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"[State after {len(tool_trace)} steps]\n{state}\n\nUse this state freely — adopt useful parts, ignore irrelevant ones, and prioritize unexplored branches.",
                        }
                    )
                    last_state_at = len(tool_trace)
                    last_state_text = state

            if len(tool_trace) >= 8 and len(tool_trace) % 4 == 0:
                if await self._check_sufficiency(user_request, tool_trace):
                    messages.append(
                        {
                            "role": "user",
                            "content": "You now have sufficient information. Provide your final answer.",
                        }
                    )

            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            logger.debug(
                "LLM response: model={}, has_tool_calls={}, tool_count={}, finish_reason={}",
                self.model,
                response.has_tool_calls,
                len(response.tool_calls),
                response.finish_reason,
            )

            if response.has_tool_calls:
                if on_progress:
                    clean = self._strip_think(response.content)
                    if clean:
                        reasoning_snippets.append(clean[:200])
                        await on_progress(clean)
                    await on_progress(self._tool_hint(response.tool_calls))

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
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )

                    has_error = isinstance(result, str) and any(
                        kw in result.lower() for kw in _ERROR_KEYWORDS
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
            else:
                final_content = self._strip_think(response.content)
                break

        return final_content, tools_used, tool_trace, total_errors, reasoning_snippets

    async def run(self) -> None:
        self._running = True
        await self._connect_mcp()
        logger.debug("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
                try:
                    response = await self._process_message(msg)
                    if response:
                        await self.bus.publish_outbound(response)
                    elif msg.channel == "cli":
                        await self.bus.publish_outbound(
                            OutboundMessage(
                                channel=msg.channel,
                                chat_id=msg.chat_id,
                                content="",
                            )
                        )
                except Exception as e:
                    logger.error("Error processing message: {}", e)
                    await self.bus.publish_outbound(
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content=f"Sorry, I encountered an error: {str(e)}",
                        )
                    )
            except asyncio.TimeoutError:
                continue

    async def close_mcp(self) -> None:
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def stop(self) -> None:
        self._running = False
        logger.info("Agent loop stopping")

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        if msg.channel == "system":
            return await self._process_system_message(msg)

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        natural_key = session_key or msg.session_key
        active_override = self.sessions.get_active_session_key(natural_key)
        key = active_override or natural_key
        session = self.sessions.get_or_create(key)

        # Handle slash commands
        cmd = msg.content.strip().lower()
        cmd_raw = msg.content.strip()
        if cmd == "/new":
            if session.messages:
                old_messages = session.messages.copy()
                old_key = session.key

                async def _consolidate_old():
                    temp = Session(key=old_key)
                    temp.messages = old_messages
                    await self._consolidate_memory(temp, archive_all=True)

                asyncio.create_task(_consolidate_old())
            name = f"s{len(self.sessions.list_sessions_for(natural_key)) + 1}"
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

        # Onboarding: language selection
        pending_lang = session.metadata.pop("_pending_onboarding_lang", None)
        if pending_lang and cmd in ("1", "2"):
            from bao.config.loader import apply_persona_language
            lang = "zh" if cmd == "1" else "en"
            apply_persona_language(self.workspace, lang)
            self.context = ContextBuilder(self.workspace, embedding_config=self.embedding_config)
            if cmd == "1":
                prompt = (
                    "你刚刚上线，这是用户第一次使用。"
                    "用户还没有自我介绍。引导他们完成初始设置："
                    "问他们的名字、想怎么称呼你、以及偏好的沟通风格。"
                    "告诉他们你会记住这些。保持简短自然，不要像填表格。"
                    "全程使用中文。"
                )
            else:
                prompt = (
                    "You just came online for the first time. "
                    "The user hasn't introduced themselves yet. Guide them through initial setup: "
                    "ask their name, what they'd like to call you, and their preferred communication style. "
                    "Tell them you'll remember these. Keep it brief and natural, not like a form. "
                    "Respond in English."
                )
            self.sessions.save(session)
            greeting = await self.process_direct(prompt, session_key=key)
            return self._reply(msg, greeting) if greeting else None
        elif pending_lang:
            # Invalid input — re-prompt
            session.metadata["_pending_onboarding_lang"] = True
            self.sessions.save(session)
            return self._reply(
                msg,
                "Please reply 1 or 2 / 请回复 1 或 2\n\n"
                "1. 中文\n"
                "2. English",
            )

        if len(session.messages) > self.memory_window and session.key not in self._consolidating:
            self._consolidating.add(session.key)

            async def _consolidate_and_unlock():
                try:
                    await self._consolidate_memory(session)
                finally:
                    self._consolidating.discard(session.key)

            asyncio.create_task(_consolidate_and_unlock())

        self._set_tool_context(msg.channel, msg.chat_id, msg.metadata.get("message_id"))
        if (t := self.tools.get("message")) and isinstance(t, MessageTool):
            t.start_turn()
        related = await asyncio.to_thread(self.context.memory.search_memory, msg.content)
        experience = await asyncio.to_thread(self.context.memory.search_experience, msg.content)
        initial_messages = self.context.build_messages(
            history=session.get_history(max_messages=self.memory_window),
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
            related_memory=related or None,
            related_experience=experience or None,
        )

        async def _bus_progress(content: str) -> None:
            if not self._should_send_progress(msg.channel, msg.chat_id, content):
                return
            logger.debug("Progress sent to {}:{}", msg.channel, msg.chat_id)
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

        (
            final_content,
            tools_used,
            tool_trace,
            total_errors,
            reasoning_snippets,
        ) = await self._run_agent_loop(
            initial_messages,
            on_progress=on_progress or _bus_progress,
        )

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

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

        session.add_message("user", msg.content)
        session.add_message(
            "assistant", final_content, tools_used=tools_used if tools_used else None
        )
        self.sessions.save(session)

        if len(session.messages) == 2 and not session.metadata.get("title"):
            asyncio.create_task(self._generate_session_title(session))

        if (t := self.tools.get("message")) and isinstance(t, MessageTool) and t._sent_in_turn:
            return None

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=msg.metadata
            or {},  # Pass through for channel-specific needs (e.g. Slack thread_ts)
        )

    async def _process_system_message(self, msg: InboundMessage) -> OutboundMessage | None:
        logger.info("Processing system message from {}", msg.sender_id)

        if ":" in msg.chat_id:
            origin_channel, origin_chat_id = msg.chat_id.split(":", 1)
        else:
            origin_channel, origin_chat_id = "cli", msg.chat_id

        session_key = f"{origin_channel}:{origin_chat_id}"
        session = self.sessions.get_or_create(session_key)
        self._set_tool_context(origin_channel, origin_chat_id)
        related = await asyncio.to_thread(self.context.memory.search_memory, msg.content)
        experience = await asyncio.to_thread(self.context.memory.search_experience, msg.content)
        initial_messages = self.context.build_messages(
            history=session.get_history(max_messages=self.memory_window),
            current_message=msg.content,
            channel=origin_channel,
            chat_id=origin_chat_id,
            related_memory=related or None,
            related_experience=experience or None,
        )
        (
            final_content,
            tools_used,
            tool_trace,
            total_errors,
            reasoning_snippets,
        ) = await self._run_agent_loop(initial_messages)

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

        session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
        session.add_message("assistant", final_content)
        self.sessions.save(session)

        return OutboundMessage(
            channel=origin_channel, chat_id=origin_chat_id, content=final_content
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

1. "history_entry": A paragraph (2-5 sentences) summarizing the key events/decisions/topics. Start with a timestamp like [YYYY-MM-DD HH:MM]. Include enough detail to be useful when found by grep search later.

2. "memory_update": The updated long-term memory content. Add any new facts: user location, preferences, personal info, habits, project context, technical decisions, tools/services used. If nothing new, return the existing content unchanged.

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
            if update := result.get("memory_update"):
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
    def _parse_llm_json(content: str | None) -> dict | None:
        text = (content or "").strip()
        if not text:
            return None
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json_repair.loads(text)
        return result if isinstance(result, dict) else None

    async def _call_utility_llm(self, system: str, prompt: str) -> dict | None:
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

    async def _call_experience_llm(self, system: str, prompt: str) -> dict | None:
        if self._experience_mode == "main":
            provider, model = self.provider, self.model
        elif self._utility_provider:
            provider, model = self._utility_provider, self._utility_model or self.model
        else:
            return None
        response = await provider.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            model=model,
            temperature=0.3,
            max_tokens=512,
        )
        return self._parse_llm_json(response.content)

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
        prompt = f"""Compress this agent execution state into a structured summary. Return JSON with exactly 3 keys:

1. "conclusions": What has been established so far — key findings, partial answers, verified facts (2-3 sentences)
2. "evidence": Sources consulted, tools used successfully, data gathered (1-2 sentences)
3. "unexplored": Branches mentioned but NOT yet executed, open questions, alternative approaches to try next (1-3 bullet points as a single string)

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
                merged = f"[Task] {task}\n[Outcome] success\n[Category] {category}\n[Quality] {quality}\n[Lessons] {lessons}"
                await asyncio.to_thread(memory.replace_merged, entries[:6], merged)
            except Exception as e:
                logger.debug("Experience merge skipped: {}", e)

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        await self._connect_mcp()
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)

        response = await self._process_message(
            msg, session_key=session_key, on_progress=on_progress
        )
        return response.content if response else ""
