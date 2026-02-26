"""Subagent manager for background task execution with progress tracking."""

import asyncio
import json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import json_repair
from loguru import logger

from bao.agent.artifacts import ArtifactStore, apply_tool_output_budget
from bao.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from bao.agent.tools.registry import ToolRegistry
from bao.agent.tools.shell import ExecTool
from bao.agent.tools.web import WebFetchTool, WebSearchTool
from bao.bus.events import InboundMessage, OutboundMessage
from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider

if TYPE_CHECKING:
    from bao.config.schema import ExecToolConfig, WebSearchConfig


_SUBAGENT_ERROR_KEYWORDS = ("error:", "traceback", "failed", "exception", "permission denied")
_PROTECTED_WRITE_DIRS = ("lancedb", "memory", ".bao")


@dataclass
class TaskStatus:
    task_id: str
    label: str
    task_description: str
    origin: dict[str, str]
    status: str = "running"  # running | completed | failed | cancelled
    iteration: int = 0
    max_iterations: int = 20
    tool_steps: int = 0
    phase: str = "starting"  # starting | thinking | tool:<name> | summarizing
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    result_summary: str | None = None
    offloaded_count: int = 0
    offloaded_chars: int = 0
    clipped_count: int = 0
    clipped_chars: int = 0
    recent_actions: list[str] = field(default_factory=list)  # last N tool call summaries


class SubagentManager:
    _MAX_COMPLETED: int = 50  # retain at most N finished tasks
    _PROGRESS_INTERVAL: int = 5  # push progress every N iterations

    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path,
        bus: MessageBus,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        search_config: "WebSearchConfig | None" = None,
        exec_config: "ExecToolConfig | None" = None,
        restrict_to_workspace: bool = False,
        max_iterations: int = 20,
        context_management: str = "observe",
        tool_output_offload_chars: int = 8000,
        tool_output_preview_chars: int = 3000,
        tool_output_hard_chars: int = 6000,
        context_compact_bytes_est: int = 240000,
        context_compact_keep_recent_tool_blocks: int = 4,
        artifact_retention_days: int = 7,
        memory_store: Any | None = None,
        image_generation_config: Any | None = None,
        desktop_config: Any | None = None,
        utility_provider: LLMProvider | None = None,
        utility_model: str | None = None,
        experience_mode: str = "utility",
    ):
        from bao.config.schema import ExecToolConfig

        self.provider = provider
        self.workspace = workspace
        self.bus = bus
        self.model = model or provider.get_default_model()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.search_config = search_config
        self.exec_config = exec_config or ExecToolConfig()
        self.restrict_to_workspace = restrict_to_workspace
        self.image_generation_config = image_generation_config
        self.desktop_config = desktop_config
        self.max_iterations = max(1, int(max_iterations))
        self._ctx_mgmt = context_management
        self._tool_offload_chars = max(1, int(tool_output_offload_chars))
        self._tool_preview_chars = max(0, int(tool_output_preview_chars))
        self._tool_hard_chars = max(500, int(tool_output_hard_chars))
        self._compact_bytes = max(50000, int(context_compact_bytes_est))
        self._compact_keep_blocks = max(1, int(context_compact_keep_recent_tool_blocks))
        self._artifact_retention_days = max(1, int(artifact_retention_days))
        self._memory = memory_store
        self._utility_provider = utility_provider
        self._utility_model = utility_model
        self._experience_mode = experience_mode.lower()
        self._artifact_cleanup_done = False
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
        self._task_statuses: dict[str, TaskStatus] = {}
        self._session_tasks: dict[str, set[str]] = {}  # session_key -> {task_id, ...}

    def set_aux_runtime(
        self,
        *,
        utility_provider: LLMProvider | None,
        utility_model: str | None,
        experience_mode: str,
    ) -> None:
        self._utility_provider = utility_provider
        self._utility_model = utility_model
        self._experience_mode = (experience_mode or "utility").lower()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def spawn(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "gateway",
        origin_chat_id: str = "direct",
        session_key: str | None = None,
    ) -> str:
        task_id = str(uuid.uuid4())[:8]
        display_label = label or (task[:30] + ("..." if len(task) > 30 else "")) or "unnamed task"
        origin = {"channel": origin_channel, "chat_id": origin_chat_id}
        if session_key:
            origin["session_key"] = session_key

        self._task_statuses[task_id] = TaskStatus(
            task_id=task_id,
            label=display_label,
            task_description=task[:200],
            origin=origin,
            max_iterations=self.max_iterations,
        )
        self._cleanup_completed()

        bg_task = asyncio.create_task(self._run_subagent(task_id, task, display_label, origin))
        self._running_tasks[task_id] = bg_task
        if session_key:
            self._session_tasks.setdefault(session_key, set()).add(task_id)

        def _cleanup(_: asyncio.Task[None]) -> None:
            self._running_tasks.pop(task_id, None)
            if session_key and (ids := self._session_tasks.get(session_key)):
                ids.discard(task_id)
                if not ids:
                    del self._session_tasks[session_key]

        bg_task.add_done_callback(_cleanup)

        logger.info("Spawned subagent [{}]: {}", task_id, display_label)
        return f"Subagent [{display_label}] started (id: {task_id}). I'll notify you when it completes."

    def get_task_status(self, task_id: str) -> TaskStatus | None:
        return self._task_statuses.get(task_id)

    def get_all_statuses(self) -> list[TaskStatus]:
        return list(self._task_statuses.values())

    def get_running_count(self) -> int:
        return len(self._running_tasks)

    async def _cancel_by_session(self, session_key: str, *, wait: bool) -> int:
        task_ids = list(self._session_tasks.get(session_key, []))  # snapshot
        tasks = [
            self._running_tasks[tid]
            for tid in task_ids
            if tid in self._running_tasks and not self._running_tasks[tid].done()
        ]
        for t in tasks:
            t.cancel()
        if wait and tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return len(tasks)

    async def cancel_by_session(self, session_key: str, *, wait: bool = True) -> int:
        """Cancel all subagents for the given session. Returns count cancelled."""
        return await self._cancel_by_session(session_key, wait=wait)

    async def cancel_task(self, task_id: str) -> str:
        at = self._running_tasks.get(task_id)
        if not at:
            return f"No running task with id '{task_id}'."
        at.cancel()
        self._running_tasks.pop(task_id, None)
        for session_key, ids in list(self._session_tasks.items()):
            if task_id in ids:
                ids.discard(task_id)
                if not ids:
                    self._session_tasks.pop(session_key, None)
        if st := self._task_statuses.get(task_id):
            st.status = "cancelled"
            st.updated_at = time.time()
        logger.info("Cancelled subagent [{}]", task_id)
        return f"Task '{task_id}' cancelled."

    # ------------------------------------------------------------------
    # Internal: status helpers
    # ------------------------------------------------------------------

    _MAX_RECENT_ACTIONS: int = 6  # keep last N tool call summaries

    def _update_status(
        self,
        task_id: str,
        *,
        iteration: int | None = None,
        phase: str | None = None,
        tool_steps: int | None = None,
        status: str | None = None,
        result_summary: str | None = None,
        action: str | None = None,
    ) -> None:
        st = self._task_statuses.get(task_id)
        if not st:
            return
        if iteration is not None:
            st.iteration = iteration
        if phase is not None:
            st.phase = phase
        if tool_steps is not None:
            st.tool_steps = tool_steps
        if status is not None:
            st.status = status
        if result_summary is not None:
            st.result_summary = result_summary
        if action is not None:
            st.recent_actions.append(action)
            if len(st.recent_actions) > self._MAX_RECENT_ACTIONS:
                st.recent_actions = st.recent_actions[-self._MAX_RECENT_ACTIONS :]
        st.updated_at = time.time()

    def _accumulate_budget(
        self, task_id: str, *, offloaded_chars: int = 0, clipped_chars: int = 0
    ) -> None:
        st = self._task_statuses.get(task_id)
        if not st:
            return
        if offloaded_chars > 0:
            st.offloaded_count += 1
            st.offloaded_chars += offloaded_chars
        if clipped_chars > 0:
            st.clipped_count += 1
            st.clipped_chars += clipped_chars
        st.updated_at = time.time()

    async def _push_milestone(
        self, task_id: str, label: str, iteration: int, max_iter: int, origin: dict[str, str]
    ) -> None:
        st = self._task_statuses.get(task_id)
        content = f"⏳ [{label}] {iteration}/{max_iter}"
        if st:
            content += f", {st.tool_steps} tools"
            if st.phase.startswith("tool:"):
                content += f" — {st.phase}"
            # Append recent actions for transparency
            if st.recent_actions:
                recent = st.recent_actions[-3:]  # show last 3 actions in milestone
                content += "\n" + "\n".join(f"  → {a}" for a in recent)
            if st.clipped_count or st.offloaded_count:
                content += (
                    f"\n  budget clip:{st.clipped_count}/{st.clipped_chars} "
                    f"offload:{st.offloaded_count}/{st.offloaded_chars}"
                )
        try:
            await self.bus.publish_outbound(
                OutboundMessage(
                    channel=origin["channel"],
                    chat_id=origin["chat_id"],
                    content=content,
                    metadata={"_progress": True, "_subagent_progress": True, "task_id": task_id},
                )
            )
        except Exception:
            logger.debug("Subagent [{}] milestone push failed (non-fatal)", task_id)

    def _cleanup_completed(self) -> None:
        finished = [(tid, st) for tid, st in self._task_statuses.items() if st.status != "running"]
        if len(finished) <= self._MAX_COMPLETED:
            return
        finished.sort(key=lambda x: x[1].updated_at)
        for tid, _ in finished[: len(finished) - self._MAX_COMPLETED]:
            self._task_statuses.pop(tid, None)

    @staticmethod
    def _strip_think(text: str | None) -> str:
        return (text or "").strip()

    @staticmethod
    def _parse_llm_json(content: str | None) -> dict[str, Any] | None:
        text = (content or "").strip()
        if not text:
            return None
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json_repair.loads(text)
        return result if isinstance(result, dict) else None

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
        if use_utility and self._utility_provider:
            provider = self._utility_provider
            model = self._utility_model or self.model
        else:
            provider = self.provider
            model = self.model

        assert provider is not None

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

    @staticmethod
    def _has_tool_error(result: str) -> bool:
        result_lower = result.lower()
        return any(kw in result_lower for kw in _SUBAGENT_ERROR_KEYWORDS)

    def _is_protected_write_path(self, path: str) -> bool:
        target = Path(path).expanduser()
        if not target.is_absolute():
            target = self.workspace / target
        try:
            resolved = target.resolve()
        except Exception:
            return False

        for rel_dir in _PROTECTED_WRITE_DIRS:
            protected_root = (self.workspace / rel_dir).resolve()
            try:
                resolved.relative_to(protected_root)
                return True
            except ValueError:
                continue
        return False

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

        prompt = f"""Compress this subagent execution state into a structured summary. Return JSON with exactly {key_count} keys:

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
            logger.debug("Subagent state compression skipped: {}", e)
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

    def _compact_messages(
        self,
        messages: list[dict[str, Any]],
        initial_messages: list[dict[str, Any]],
        last_state_text: str | None,
        artifact_store: ArtifactStore | None,
    ) -> list[dict[str, Any]]:
        if artifact_store is not None:
            try:
                artifact_store.archive_json(
                    "evicted_messages", "subagent_compacted_context", messages
                )
            except Exception as exc:
                logger.warning("subagent ctx[L2] archive failed: {}", exc)

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
        return system_msgs + user_msgs + recent_msgs

    @staticmethod
    def _budget_items(items: list[str], max_items: int, max_chars: int) -> list[str]:
        result: list[str] = []
        total = 0
        for item in items:
            if len(result) >= max_items:
                break
            remaining = max_chars - total
            if remaining <= 0:
                break
            piece = item if len(item) <= remaining else item[:remaining]
            result.append(piece)
            total += len(piece)
        return result

    async def _get_related_memory(self, task: str) -> tuple[list[str], list[str]]:
        if self._memory is None:
            return [], []
        related_mem, related_exp = await asyncio.gather(
            asyncio.to_thread(self._memory.search_memory, task, 3),
            asyncio.to_thread(self._memory.search_experience, task, 3),
            return_exceptions=True,
        )
        mem = related_mem if isinstance(related_mem, list) else []
        exp = related_exp if isinstance(related_exp, list) else []
        return mem, exp

    # ------------------------------------------------------------------
    # Internal: subagent execution
    # ------------------------------------------------------------------

    async def _run_subagent(
        self,
        task_id: str,
        task: str,
        label: str,
        origin: dict[str, str],
    ) -> None:
        logger.info("Subagent [{}] starting task: {}", task_id, label)
        artifact_store: ArtifactStore | None = None

        try:
            tools = ToolRegistry()
            allowed_dir = self.workspace if self.restrict_to_workspace else None
            tools.register(ReadFileTool(workspace=self.workspace, allowed_dir=allowed_dir))
            tools.register(WriteFileTool(workspace=self.workspace, allowed_dir=allowed_dir))
            tools.register(EditFileTool(workspace=self.workspace, allowed_dir=allowed_dir))
            tools.register(ListDirTool(workspace=self.workspace, allowed_dir=allowed_dir))
            tools.register(
                ExecTool(
                    working_dir=str(self.workspace),
                    timeout=self.exec_config.timeout,
                    restrict_to_workspace=self.restrict_to_workspace,
                    path_append=self.exec_config.path_append,
                    sandbox_mode=self.exec_config.sandbox_mode,
                )
            )
            channel = origin.get("channel", "gateway")
            chat_id = origin.get("chat_id", "direct")
            coding_tools: list[str] = []
            if shutil.which("opencode"):
                from bao.agent.tools.opencode import OpenCodeDetailsTool, OpenCodeTool

                oc_tool = OpenCodeTool(workspace=self.workspace, allowed_dir=allowed_dir)
                oc_details = OpenCodeDetailsTool()
                oc_tool.set_context(channel, chat_id)
                oc_details.set_context(channel, chat_id)
                tools.register(oc_tool)
                tools.register(oc_details)
                coding_tools.append("opencode")
            if shutil.which("codex"):
                from bao.agent.tools.codex import CodexDetailsTool, CodexTool

                cx_tool = CodexTool(workspace=self.workspace, allowed_dir=allowed_dir)
                cx_details = CodexDetailsTool()
                cx_tool.set_context(channel, chat_id)
                cx_details.set_context(channel, chat_id)
                tools.register(cx_tool)
                tools.register(cx_details)
                coding_tools.append("codex")
            if shutil.which("claude"):
                from bao.agent.tools.claudecode import ClaudeCodeDetailsTool, ClaudeCodeTool

                cc_tool = ClaudeCodeTool(workspace=self.workspace, allowed_dir=allowed_dir)
                cc_details = ClaudeCodeDetailsTool()
                cc_tool.set_context(channel, chat_id)
                cc_details.set_context(channel, chat_id)
                tools.register(cc_tool)
                tools.register(cc_details)
                coding_tools.append("claudecode")
            # Image generation (conditional)
            if self.image_generation_config and self.image_generation_config.api_key:
                from bao.agent.tools.image_gen import ImageGenTool
                tools.register(ImageGenTool(
                    api_key=self.image_generation_config.api_key,
                    model=self.image_generation_config.model,
                    base_url=self.image_generation_config.base_url,
                ))
            # Desktop automation (conditional: enabled in config + deps available)
            if self.desktop_config and self.desktop_config.enabled:
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
                    tools.register(ScreenshotTool())
                    tools.register(ClickTool())
                    tools.register(TypeTextTool())
                    tools.register(KeyPressTool())
                    tools.register(ScrollTool())
                    tools.register(DragTool())
                    tools.register(GetScreenInfoTool())
                except ImportError:
                    pass
            search_tool = WebSearchTool(search_config=self.search_config)
            has_search = bool(
                search_tool.brave_key or search_tool.tavily_key or search_tool.exa_key
            )
            if has_search:
                tools.register(search_tool)
            tools.register(WebFetchTool())

            related_memory, related_experience = await self._get_related_memory(task)

            if not self._artifact_cleanup_done and self._ctx_mgmt in ("auto", "aggressive"):
                self._artifact_cleanup_done = True
                try:
                    ArtifactStore(
                        self.workspace, "_stale_", self._artifact_retention_days
                    ).cleanup_stale()
                except Exception as exc:
                    logger.warning("subagent ctx stale cleanup failed: {}", exc)

            # Build messages with subagent-specific prompt
            system_prompt = self._build_subagent_prompt(
                task,
                channel=origin.get("channel"),
                has_search=has_search,
                coding_tools=coding_tools,
                related_memory=related_memory,
                related_experience=related_experience,
            )
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task},
            ]
            initial_messages = list(messages)

            artifact_store = (
                ArtifactStore(self.workspace, f"subagent_{task_id}", self._artifact_retention_days)
                if self._ctx_mgmt in ("auto", "aggressive")
                else None
            )

            max_iterations = self.max_iterations
            iteration = 0
            final_result: str | None = None
            failed_directions: list[str] = []
            consecutive_errors = 0
            tool_step = 0
            tool_trace: list[str] = []
            reasoning_snippets: list[str] = []
            last_state_attempt_at = 0
            last_state_text: str | None = None

            while iteration < max_iterations:
                iteration += 1

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
                                "content": (
                                    f"[State after {len(tool_trace)} steps]\n{state}\n\n"
                                    "Use this state freely — adopt useful parts, ignore irrelevant ones, and prioritize unexplored branches."
                                ),
                            }
                        )
                        last_state_text = state

                if len(tool_trace) >= 8 and len(tool_trace) % 4 == 0:
                    if await self._check_sufficiency(task, tool_trace):
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
                            artifact_store=artifact_store,
                        )

                self._update_status(task_id, iteration=iteration, phase="thinking")

                response = await self.provider.chat(
                    messages=messages,
                    tools=tools.get_definitions(),
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                # Strip _image base64 from messages after provider has processed them
                for _m in messages:
                    _m.pop("_image", None)

                if response.has_tool_calls:
                    clean = self._strip_think(response.content)
                    if clean:
                        reasoning_snippets.append(clean[:200])
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
                    messages.append(
                        {
                            "role": "assistant",
                            "content": response.content or "",
                            "tool_calls": tool_call_dicts,
                        }
                    )

                    for tool_call in response.tool_calls:
                        # Build action summary: tool_name(first_arg_preview)
                        first_arg_value = (
                            next(iter(tool_call.arguments.values()), "")
                            if tool_call.arguments
                            else ""
                        )
                        action_summary = f"{tool_call.name}({str(first_arg_value)[:50]})"
                        self._update_status(
                            task_id,
                            phase=f"tool:{tool_call.name}",
                            tool_steps=tool_step + 1,
                            action=action_summary,
                        )

                        args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                        logger.debug(
                            "Subagent [{}] executing: {} with arguments: {}",
                            task_id,
                            tool_call.name,
                            args_str,
                        )
                        if (
                            tool_call.name in {"write_file", "edit_file"}
                            and isinstance(first_arg_value, str)
                            and self._is_protected_write_path(first_arg_value)
                        ):
                            raw_result = f"Error: write access to protected path is blocked: {first_arg_value}"
                        else:
                            raw_result = await tools.execute(tool_call.name, tool_call.arguments)
                        result_text = raw_result if isinstance(raw_result, str) else str(raw_result)
                        result, budget_event = apply_tool_output_budget(
                            store=artifact_store,
                            tool_name=tool_call.name,
                            tool_call_id=tool_call.id,
                            result=result_text,
                            offload_chars=self._tool_offload_chars,
                            preview_chars=self._tool_preview_chars,
                            hard_chars=self._tool_hard_chars,
                            ctx_mgmt=self._ctx_mgmt,
                        )
                        self._accumulate_budget(
                            task_id,
                            offloaded_chars=budget_event.offloaded_chars,
                            clipped_chars=budget_event.hard_clipped_chars,
                        )
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
                                logger.warning("subagent: failed to read screenshot {}: {}", _ss_path, _ss_err)
                        tool_msg: dict[str, Any] = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.name,
                            "content": result,
                        }
                        if _screenshot_image_b64:
                            tool_msg["_image"] = _screenshot_image_b64
                        messages.append(tool_msg)
                        tool_step += 1
                        has_error = isinstance(result, str) and self._has_tool_error(result)
                        tool_trace.append(
                            f"{tool_call.name}({args_str[:60]}) → {'ERROR' if has_error else 'ok'}: {(result or '')[:100]}"
                        )
                        if has_error:
                            consecutive_errors += 1
                            failed_directions.append(
                                f"{tool_call.name}({str(first_arg_value)[:60]})"
                            )
                        else:
                            consecutive_errors = 0
                            failed_directions.clear()

                    if consecutive_errors >= 2:
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    f"Already tried and failed: {'; '.join(failed_directions[-3:])}."
                                    " Try a different approach."
                                ),
                            }
                        )
                    elif tool_step >= 8 and tool_step % 4 == 0:
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    f"[Progress: {tool_step} steps completed]"
                                    " Focus on completing the task efficiently."
                                ),
                            }
                        )

                    if iteration % self._PROGRESS_INTERVAL == 0:
                        await self._push_milestone(
                            task_id, label, iteration, max_iterations, origin
                        )
                else:
                    final_result = self._strip_think(response.content)
                    break

            if final_result is None:
                final_result = "Task completed but no final response was generated."

            self._update_status(
                task_id,
                phase="completed",
                status="completed",
                iteration=iteration,
                tool_steps=tool_step,
                result_summary=final_result[:500] if final_result else None,
            )

            logger.info("Subagent [{}] completed successfully", task_id)
            await self._announce_result(task_id, label, task, final_result, origin, "ok")

        except asyncio.CancelledError:
            self._update_status(task_id, status="cancelled", phase="cancelled")
            logger.info("Subagent [{}] was cancelled", task_id)

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self._update_status(
                task_id,
                status="failed",
                phase="failed",
                result_summary=error_msg[:500],
            )
            logger.error("Subagent [{}] failed: {}", task_id, e)
            await self._announce_result(task_id, label, task, error_msg, origin, "error")

    async def _announce_result(
        self,
        task_id: str,
        label: str,
        task: str,
        result: str,
        origin: dict[str, str],
        status: str,
    ) -> None:
        status_text = "completed successfully" if status == "ok" else "failed"

        announce_content = f"""[Subagent '{label}' {status_text}]

Task: {task}

Result:
{result}

Summarize this naturally for the user. Keep it brief (1-2 sentences). Do not mention technical details like "subagent" or task IDs."""

        msg = InboundMessage(
            channel="system",
            sender_id="subagent",
            chat_id=f"{origin['channel']}:{origin['chat_id']}",
            content=announce_content,
            metadata={"session_key": origin["session_key"]}
            if isinstance(origin.get("session_key"), str)
            else {},
        )

        await self.bus.publish_inbound(msg)
        logger.debug(
            "Subagent [{}] announced result to {}:{}", task_id, origin["channel"], origin["chat_id"]
        )

    def _build_subagent_prompt(
        self,
        task: str,
        *,
        channel: str | None,
        has_search: bool = False,
        coding_tools: list[str] | None = None,
        related_memory: list[str] | None = None,
        related_experience: list[str] | None = None,
    ) -> str:
        """Build a focused system prompt for the subagent."""
        from bao.agent.context import (
            MAX_EXPERIENCE_CHARS,
            MAX_EXPERIENCE_ITEMS,
            MAX_MEMORY_CHARS,
            MAX_MEMORY_ITEMS,
            ContextBuilder,
            format_current_time,
        )

        search_capability = "\n- Search the web and fetch web pages" if has_search else ""

        coding_capability = ""
        if coding_tools:
            names = ", ".join(f"`{t}`" for t in coding_tools)
            coding_capability = (
                f"\n- Delegate complex coding tasks to coding agents: {names}\n"
                "  PREFER coding agents for multi-file changes, refactoring, debugging, "
                "and feature implementation over manual exec+read_file+write_file. "
                "Read the corresponding skill for usage: skills/{name}/SKILL.md"
            )

        format_hint = ContextBuilder.get_channel_format_hint(channel)
        format_section = f"\n\n## Response Format\n{format_hint}" if format_hint else ""
        memory_section = ""
        if related_memory:
            budgeted_memory = self._budget_items(
                related_memory,
                max_items=MAX_MEMORY_ITEMS,
                max_chars=MAX_MEMORY_CHARS,
            )
            if budgeted_memory:
                memory_section += "\n\n## Related Memory\n" + "\n---\n".join(budgeted_memory)
        if related_experience:
            budgeted_experience = self._budget_items(
                related_experience,
                max_items=MAX_EXPERIENCE_ITEMS,
                max_chars=MAX_EXPERIENCE_CHARS,
            )
            if budgeted_experience:
                memory_section += (
                    "\n\n## Past Experience (lessons from similar tasks)\n"
                    + "\n---\n".join(budgeted_experience)
                )

        return f"""# Subagent

Current time: {format_current_time(include_weekday=False)}

You are a subagent spawned by the main agent to complete a specific task.

## Rules
1. Stay focused - complete only the assigned task, nothing else
2. Your final response will be reported back to the main agent
3. Do not initiate conversations or take on side tasks
4. Be concise but informative in your findings

## What You Can Do
- Read and write files in the workspace
- Execute shell commands
{search_capability}{coding_capability}
- Complete the task thoroughly

## What You Cannot Do
- Send messages directly to users (no message tool available)
- Spawn other subagents
- Access the main agent's conversation history
- Write or mutate memory/experience (read-only context only)

## Workspace
Your workspace is at: {self.workspace}
Skills are available at: {self.workspace}/skills/ (read SKILL.md files as needed)

When you have completed the task, provide a clear summary of your findings or actions.{memory_section}{format_section}"""
