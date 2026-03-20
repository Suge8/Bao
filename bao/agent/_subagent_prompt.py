from __future__ import annotations

import asyncio
from pathlib import Path

from bao.agent import shared
from bao.agent.context import ContextBuilder

from ._subagent_types import PrepareMessagesRequest, SubagentPromptRequest

_BUILTIN_SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"


class SubagentPromptMixin:
    async def _compress_state(
        self,
        tool_trace: list[str],
        reasoning_snippets: list[str],
        failed_directions: list[str],
        previous_state: str | None = None,
    ) -> str | None:
        return await shared.compress_state(
            shared.CompressStateRequest(
                tool_trace=tool_trace,
                reasoning_snippets=reasoning_snippets,
                failed_directions=failed_directions,
                previous_state=previous_state,
                experience_mode=self._experience_mode,
                llm_fn=self._call_experience_llm,
                label="subagent",
            )
        )

    async def _check_sufficiency(
        self, user_request: str, tool_trace: list[str], last_state_text: str | None = None
    ) -> bool:
        return await shared.check_sufficiency(
            shared.SufficiencyRequest(
                user_request=user_request,
                tool_trace=tool_trace,
                experience_mode=self._experience_mode,
                llm_fn=self._call_experience_llm,
                last_state_text=last_state_text,
            )
        )

    def _compact_messages(
        self,
        messages: list[dict[str, object]],
        initial_messages: list[dict[str, object]],
        last_state_text: str | None,
        artifact_store,
    ) -> list[dict[str, object]]:
        return shared.compact_messages(
            shared.CompactMessagesRequest(
                messages=messages,
                initial_messages=initial_messages,
                last_state_text=last_state_text,
                artifact_store=artifact_store,
                keep_blocks=self._compact_keep_blocks,
                label="subagent",
            )
        )

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
        bundle = await asyncio.to_thread(
            self._memory.recall,
            task,
            related_limit=3,
            experience_limit=3,
            include_long_term=False,
        )
        return list(bundle.related_memory), list(bundle.related_experience)

    def _prepare_subagent_messages(
        self, request: PrepareMessagesRequest
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        system_prompt = self._build_subagent_prompt(
            SubagentPromptRequest(
                task=request.task,
                channel=request.channel,
                has_search=request.has_search,
                has_browser=request.has_browser,
                coding_tools=request.coding_tools,
                coding_backend_issues=request.coding_backend_issues,
                related_memory=request.related_memory,
                related_experience=request.related_experience,
            )
        )
        history = (
            self._child_session_history(request.child_session_key) if request.child_session_key else []
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}, *history]
        current = self.get_task_status(request.task_id)
        resume_ctx = current.resume_context if current else None
        if not resume_ctx and request.context_from:
            resume_ctx, warning = self._resolve_resume_context(request.context_from)
            if warning is not None:
                from loguru import logger

                logger.debug(
                    "context_from={} not found or not finished, ignoring",
                    request.context_from,
                )
        if resume_ctx:
            messages.insert(1, {"role": "user", "content": resume_ctx})
        if not history:
            messages.append({"role": "user", "content": request.task})
        return messages, list(messages)

    def _build_subagent_prompt(self, request: SubagentPromptRequest) -> str:
        from bao.agent.context import format_current_time

        search_capability = "\n- Search the web and fetch web pages" if request.has_search else ""
        browser_capability = (
            "\n- Control a browser for interactive pages, forms, screenshots, and DOM snapshots"
            if request.has_browser
            else ""
        )
        coding_capability = self._coding_capability_section(
            request.coding_tools or [],
            request.coding_backend_issues or [],
        )
        format_hint = ContextBuilder.get_channel_format_hint(request.channel)
        format_section = f"\n\n## Response Format\n{format_hint}" if format_hint else ""
        memory_section = self._memory_section(
            related_memory=request.related_memory or [],
            related_experience=request.related_experience or [],
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
{search_capability}{browser_capability}{coding_capability}
- Complete the task thoroughly

## What You Cannot Do
- Send messages directly to users (no direct notify tool available)
- Spawn other subagents
- Access the main agent's conversation history
- Write or mutate memory/experience (read-only context only)

## Workspace
Your workspace is at: {self.workspace}
Skills may live in either of these locations:
- workspace overrides: {self.workspace}/skills/
- built-in skills: {_BUILTIN_SKILLS_ROOT}
If the task matches a skill in those locations, read that `SKILL.md` before any substantive action.

When you have completed the task, provide a clear summary of your findings or actions.{memory_section}{format_section}"""

    def _coding_capability_section(
        self,
        coding_tools: list[str],
        coding_backend_issues: list[str],
    ) -> str:
        sections: list[str] = []
        if coding_tools:
            names = ", ".join(coding_tools)
            section = (
                f"\n- coding_agent(agent=...): delegate coding to {names}.\n"
                "  PREFER coding_agent for multi-file changes, refactoring, debugging, "
                "and feature implementation over manual exec+read_file+write_file. "
                "Use the backend or CLI default model unless the user explicitly asks for an override "
                "or a backend issue forces a different model. "
                "Read the skill for usage: `bao/skills/coding-agent/SKILL.md` "
                "(or `skills/coding-agent/SKILL.md` if overridden in the workspace)."
            )
            if "opencode" in coding_tools and self._oh_my_opencode_detected():
                section += (
                    "\n  OhMyOpenCode detected: use `ulw` prefix in opencode "
                    "prompts for enhanced orchestration mode."
                )
            sections.append(section)
        if coding_backend_issues:
            lines = "\n".join(f"  - {item}" for item in coding_backend_issues)
            sections.append(
                "\n- Some coding backends are unavailable right now. "
                "Do not keep retrying them blindly.\n"
                f"{lines}"
            )
        return "".join(sections)

    def _oh_my_opencode_detected(self) -> bool:
        from pathlib import Path

        candidate_paths = [
            self.workspace / ".opencode/oh-my-opencode.jsonc",
            self.workspace / ".opencode/oh-my-opencode.json",
            Path.home() / ".config/opencode/oh-my-opencode.jsonc",
            Path.home() / ".config/opencode/oh-my-opencode.json",
        ]
        return any(path.exists() for path in candidate_paths)

    def _memory_section(
        self, *, related_memory: list[str], related_experience: list[str]
    ) -> str:
        sections: list[str] = []
        budgeted_memory = self._budget_items(
            related_memory,
            max_items=self._memory_policy.related_memory_limit,
            max_chars=self._memory_policy.related_memory_chars,
        )
        if budgeted_memory:
            sections.append("\n\n## Related Memory\n" + "\n---\n".join(budgeted_memory))
        budgeted_experience = self._budget_items(
            related_experience,
            max_items=self._memory_policy.related_experience_limit,
            max_chars=self._memory_policy.related_experience_chars,
        )
        if budgeted_experience:
            sections.append(
                "\n\n## Past Experience (lessons from similar tasks)\n"
                + "\n---\n".join(budgeted_experience)
            )
        return "".join(sections)
