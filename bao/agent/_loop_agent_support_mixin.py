from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from bao.agent import commands, experience, shared
from bao.agent._loop_constants import GREETING_WORDS as _GREETING_WORDS
from bao.agent._loop_memory_consolidation import consolidate_memory as _consolidate_memory_impl
from bao.agent._loop_memory_ui import handle_memory_command as _handle_memory_command_impl
from bao.agent._loop_memory_ui import handle_memory_input as _handle_memory_input_impl
from bao.agent._loop_session_title import build_title_prompt as _build_title_prompt
from bao.agent._loop_session_title import fallback_title as _fallback_title
from bao.agent._loop_session_title import find_title_messages as _find_title_messages
from bao.agent._loop_session_title import normalize_generated_title as _normalize_generated_title
from bao.agent._loop_types import extract_text as _extract_text
from bao.agent._loop_user_message_models import ProcessDirectRequest, ProcessMessageOptions
from bao.bus.events import InboundMessage, OutboundMessage
from bao.session.manager import Session

if TYPE_CHECKING:
    from bao.agent.artifacts import ArtifactStore
    from bao.agent.memory import MemoryStore


class LoopAgentSupportMixin:
    @staticmethod
    def _reply(msg: InboundMessage, content: str) -> OutboundMessage:
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
        except Exception as exc:
            self.provider = old_provider
            self.subagents.provider = old_provider
            self.subagents.model = old_model
            self.model = old_model
            logger.warning("⚠️ Provider 重建失败 / rebuild failed for {}: {}", new_model, exc)
            raise

    def _clear_memory_state(self, session: Session) -> None:
        for key in ("_pending_memory_list", "_pending_memory_detail", "_pending_memory_delete", "_pending_memory_edit", "_memory_entries", "_memory_selected_index"):
            session.metadata.pop(key, None)

    def _clear_model_session_state(self, session: Session) -> None:
        session.metadata.pop("_pending_model_select", None)
        session.metadata.pop("_pending_session_select", None)
        session.metadata.pop("_session_list_keys", None)

    def _clear_interactive_state(self, session: Session) -> bool:
        keys = ("_pending_memory_list", "_pending_memory_detail", "_pending_memory_delete", "_pending_memory_edit", "_memory_entries", "_memory_selected_index", "_pending_model_select", "_pending_session_select")
        if not any(key in session.metadata for key in keys):
            return False
        self._clear_memory_state(session)
        self._clear_model_session_state(session)
        return True

    async def _handle_memory_command(self, msg: InboundMessage, session: Session) -> OutboundMessage:
        return await _handle_memory_command_impl(self, msg, session)

    async def _handle_memory_input(self, msg: InboundMessage, session: Session) -> OutboundMessage:
        return await _handle_memory_input_impl(self, msg, session)

    async def _consolidate_memory(self, session: Session, archive_all: bool = False) -> None:
        await _consolidate_memory_impl(self, session, archive_all)

    async def _call_utility_llm(self, system: str, prompt: str) -> dict[str, Any] | None:
        provider = self._utility_provider if self._utility_provider is not None and self._utility_model else self.provider
        model = self._utility_model if self._utility_provider is not None and self._utility_model else self.model
        response = await provider.chat(shared.ChatRequest(messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}], model=model, temperature=0.3, max_tokens=512, service_tier=self.service_tier, source="utility"))
        return shared.parse_llm_json(response.content)

    async def _generate_session_title(self, session: Session) -> None:
        if session.metadata.get("title"):
            return
        user_msg, assistant_msg = _find_title_messages(session.messages, extract_text=_extract_text, greeting_words=_GREETING_WORDS)
        if not user_msg or not assistant_msg:
            return
        prompt = _build_title_prompt(user_content=_extract_text(user_msg["content"])[:500], assistant_content=_extract_text(assistant_msg["content"])[:300])
        fallback_text = _fallback_title(user_msg["content"], extract_text=_extract_text)
        try:
            result = await self._call_utility_llm("You are a conversation title generator. Respond only with valid JSON.", prompt)
            title = _normalize_generated_title(result)
            if title and not session.metadata.get("title"):
                session.metadata["title"] = title[:30]
                self.sessions.save(session)
                logger.debug("Session title generated: {} → {}", session.key, title[:30])
                return
        except Exception as exc:
            logger.debug("Session title generation failed: {}", exc)
        try:
            if fallback_text and not session.metadata.get("title"):
                session.metadata["title"] = fallback_text
                self.sessions.save(session)
        except Exception:
            pass

    async def _call_experience_llm(self, system: str, prompt: str) -> dict[str, Any] | None:
        return await shared.call_experience_llm(shared.ExperienceLLMRequest(system=system, prompt=prompt, experience_mode=self._experience_mode, provider=self.provider, model=self.model, utility_provider=self._utility_provider, utility_model=self._utility_model, service_tier=self.service_tier))

    def _compact_messages(self, messages: list[dict[str, Any]], initial_messages: list[dict[str, Any]], last_state_text: str | None, artifact_store: ArtifactStore | None) -> list[dict[str, Any]]:
        return shared.compact_messages(shared.CompactMessagesRequest(messages=messages, initial_messages=initial_messages, last_state_text=last_state_text, artifact_store=artifact_store, keep_blocks=self._compact_keep_blocks))

    async def _compress_state(self, tool_trace: list[str], reasoning_snippets: list[str], failed_directions: list[str], previous_state: str | None = None) -> str | None:
        return await shared.compress_state(shared.CompressStateRequest(tool_trace=tool_trace, reasoning_snippets=reasoning_snippets, failed_directions=failed_directions, previous_state=previous_state, experience_mode=self._experience_mode, llm_fn=self._call_experience_llm, label="agent"))

    async def _check_sufficiency(self, user_request: str, tool_trace: list[str], last_state_text: str | None = None) -> bool:
        return await shared.check_sufficiency(shared.SufficiencyRequest(user_request=user_request, tool_trace=tool_trace, experience_mode=self._experience_mode, llm_fn=self._call_experience_llm, last_state_text=last_state_text))

    def _maybe_learn_experience(self, request: "ExperienceLearningRequest") -> None:
        if self._experience_mode == "none":
            return
        if request.should_summarize:
            asyncio.create_task(
                experience.summarize_experience(
                    experience.ExperienceSummaryRequest(
                        memory=cast("MemoryStore", cast(object, self.context.memory)),
                        llm_fn=self._call_utility_llm,
                        user_request=request.user_request,
                        final_response=request.final_response,
                        tools_used=request.tools_used,
                        tool_trace=request.tool_trace,
                        total_errors=request.total_errors,
                        reasoning_snippets=request.reasoning_snippets,
                    )
                )
            )
        if request.should_merge:
            asyncio.create_task(experience.merge_and_cleanup_experiences(cast("MemoryStore", cast(object, self.context.memory)), self._call_utility_llm))

    async def process_direct(self, request: ProcessDirectRequest) -> str:
        await self._connect_mcp()
        wake_request = request.to_wake_request()
        msg = wake_request.to_inbound_message(sender_id="user")
        response = await self._process_message(
            msg,
            ProcessMessageOptions(
                session_key=wake_request.route.session_key,
                on_progress=wake_request.on_progress,
                on_event=wake_request.on_event,
            ),
        )
        return response.content if response else ""


@dataclass(slots=True)
class ExperienceLearningRequest:
    session: Session
    user_request: str
    final_response: str
    tools_used: list[str]
    tool_trace: list[str]
    total_errors: int
    reasoning_snippets: list[str] | None

    @property
    def should_summarize(self) -> bool:
        return len(self.tools_used) >= 3 or self.total_errors >= 2

    @property
    def should_merge(self) -> bool:
        return len(self.session.messages) % 10 == 0
