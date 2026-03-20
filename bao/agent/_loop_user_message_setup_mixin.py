from __future__ import annotations

import asyncio

from loguru import logger

from bao.agent import commands
from bao.agent._loop_onboarding_support import (
    PERSONA_EXTRACT_SYSTEM,
    build_context_builder,
    build_onboarding_confirmation_message,
    build_persona_extract_prompt,
)
from bao.agent._loop_types import archive_all_signature as _archive_all_signature
from bao.bus.events import InboundMessage, OutboundMessage
from bao.command_text import build_help_text, extract_command_name, format_new_session_started
from bao.session.manager import Session

_PENDING_MEMORY_KEYS = (
    "_pending_memory_list",
    "_pending_memory_detail",
    "_pending_memory_delete",
    "_pending_memory_edit",
)


class ReplyFlowError(Exception):
    def __init__(self, response: OutboundMessage):
        self.response = response
        super().__init__("reply")


class LoopUserMessageSetupMixin:
    async def _cleanup_stale_artifacts_if_needed(self) -> None:
        if self._artifact_cleanup_done:
            return
        self._artifact_cleanup_done = True
        try:
            from bao.agent.artifacts import ArtifactStore

            ArtifactStore(self.state_root, "_stale_", self._artifact_retention_days).cleanup_stale()
        except Exception as exc:
            logger.debug("ctx stale cleanup failed: {}", exc)

    async def _handle_user_command(
        self,
        msg: InboundMessage,
        session: Session,
        natural_key: str,
    ) -> OutboundMessage | None:
        cmd = msg.content.strip().lower()
        if cmd.startswith("/") and self._clear_interactive_state(session):
            self.sessions.save(session)
        command_response = await self._handle_primary_user_command(cmd, msg, session, natural_key)
        if command_response is not None:
            return command_response
        selection_response = self._handle_pending_selection(
            cmd,
            msg,
            session,
            natural_key,
            (
                session.metadata.pop("_pending_model_select", None),
                session.metadata.pop("_pending_session_select", None),
                session.metadata.pop("_session_list_keys", None),
            ),
        )
        if selection_response is not None:
            return selection_response
        if self._has_pending_memory_input(session):
            return await self._handle_memory_input(msg, session)
        return None

    async def _handle_primary_user_command(
        self,
        cmd: str,
        msg: InboundMessage,
        session: Session,
        natural_key: str,
    ) -> OutboundMessage | None:
        command_name = extract_command_name(cmd)
        if command_name == "new":
            await self._archive_current_session_if_needed(session)
            return self._start_new_session(msg, natural_key)
        if command_name == "delete":
            return self._delete_current_session(msg, session, natural_key)
        if command_name == "help":
            return self._reply(msg, self._help_text())
        if command_name == "model":
            return commands.handle_model_command(
                commands.ModelCommandRequest(
                    cmd=cmd,
                    msg=msg,
                    session=session,
                    available_models=self.available_models,
                    current_model=self.model,
                    sessions=self.sessions,
                    apply_fn=self._apply_model_switch,
                )
            )
        if command_name == "session":
            return commands.handle_session_command(msg, natural_key, sessions=self.sessions)
        if command_name == "memory":
            return await self._handle_memory_command(msg, session)
        return None

    def _handle_pending_selection(
        self,
        cmd: str,
        msg: InboundMessage,
        session: Session,
        natural_key: str,
        selection_state: tuple[object, object, object],
    ) -> OutboundMessage | None:
        pending, pending_session, cached_keys = selection_state
        if not cmd.isdigit():
            return None
        if pending:
            return commands.switch_model(
                commands.ModelSwitchRequest(
                    idx=int(cmd),
                    msg=msg,
                    session=session,
                    available_models=self.available_models,
                    current_model=self.model,
                    sessions=self.sessions,
                    apply_fn=self._apply_model_switch,
                )
            )
        if not pending_session:
            return None
        self.sessions.save(session)
        return commands.select_session(
            int(cmd),
            msg,
            natural_key,
            sessions=self.sessions,
            cached_keys=cached_keys,
        )

    @staticmethod
    def _has_pending_memory_input(session: Session) -> bool:
        return any(session.metadata.get(key) for key in _PENDING_MEMORY_KEYS)

    @staticmethod
    def _help_text() -> str:
        return build_help_text()

    async def _archive_current_session_if_needed(self, session: Session) -> None:
        if not session.messages:
            return
        archive_sig = _archive_all_signature(session.messages.copy())
        last_archive_sig = str(session.metadata.get("_last_archive_all_sig", ""))
        if not archive_sig or archive_sig == last_archive_sig:
            return
        old_messages = session.messages.copy()
        old_metadata = dict(session.metadata)
        temp = Session(
            key=session.key,
            messages=old_messages,
            metadata=old_metadata,
            last_consolidated=session.last_consolidated,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

        async def _consolidate_old() -> None:
            await self._consolidate_memory(temp, archive_all=True)

        session.metadata["_last_archive_all_sig"] = archive_sig
        self.sessions.save(session)
        asyncio.create_task(_consolidate_old())

    def _start_new_session(self, msg: InboundMessage, natural_key: str) -> OutboundMessage:
        idx = len(self.sessions.list_sessions_for(natural_key)) + 1
        name = f"s{idx}"
        while self.sessions.session_exists(f"{natural_key}::{name}"):
            idx += 1
            name = f"s{idx}"
        commands.create_and_switch(self.sessions, natural_key, name)
        return self._reply(msg, format_new_session_started(name))

    def _delete_current_session(self, msg: InboundMessage, session: Session, natural_key: str) -> OutboundMessage:
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

    async def _apply_onboarding_if_needed(self, msg: InboundMessage, session: Session) -> InboundMessage:
        onboarding_stage = self._resolve_onboarding_stage(msg)
        if onboarding_stage == "lang_select":
            return await self._handle_language_selection_onboarding(msg, session)
        if onboarding_stage != "persona_setup":
            return msg
        return await self._handle_persona_setup_onboarding(msg)

    def _resolve_onboarding_stage(self, msg: InboundMessage) -> str:
        from bao.config.onboarding import detect_onboarding_stage

        if msg.channel == "system":
            return "ready"
        return detect_onboarding_stage(self.prompt_root)

    async def _handle_language_selection_onboarding(
        self,
        msg: InboundMessage,
        session: Session,
    ) -> InboundMessage:
        from bao.config.onboarding import (
            LANG_PICKER,
            PERSONA_GREETING,
            write_heartbeat,
            write_instructions,
        )

        cmd = msg.content.strip().lower()
        if cmd not in ("1", "2"):
            raise ReplyFlowError(self._reply(msg, LANG_PICKER))
        lang = "zh" if cmd == "1" else "en"
        self._write_onboarding_templates(lang, write_instructions, write_heartbeat)
        self._rebuild_context()
        greeting = PERSONA_GREETING[lang]
        session.add_message("assistant", greeting)
        self.sessions.save(session)
        raise ReplyFlowError(self._reply(msg, greeting))

    async def _handle_persona_setup_onboarding(self, msg: InboundMessage) -> InboundMessage:
        from bao.config.onboarding import infer_language

        lang = infer_language(self.prompt_root)
        profile = await self._extract_onboarding_profile(msg.content)
        if profile:
            self._write_persona_profile(lang, profile)
        return build_onboarding_confirmation_message(msg, lang=lang)

    def _write_onboarding_templates(self, lang: str, write_instructions, write_heartbeat) -> None:
        for writer, description in (
            (write_instructions, "instructions"),
            (write_heartbeat, "heartbeat"),
        ):
            try:
                writer(self.prompt_root, lang)
            except Exception as exc:
                logger.debug("Failed to write {} template: {}", description, exc)

    async def _extract_onboarding_profile(self, content: str):
        try:
            return await self._call_utility_llm(
                PERSONA_EXTRACT_SYSTEM,
                build_persona_extract_prompt(content),
            )
        except Exception:
            return None

    def _write_persona_profile(self, lang: str, profile) -> None:
        from bao.config.onboarding import write_persona_profile

        try:
            write_persona_profile(self.prompt_root, lang, profile)
            self._rebuild_context()
        except Exception as exc:
            logger.debug("Failed to write persona profile: {}", exc)

    def _rebuild_context(self) -> None:
        self.context = build_context_builder(
            workspace=self.workspace,
            prompt_root=self.prompt_root,
            state_root=self.state_root,
            embedding_config=self.embedding_config,
            memory_policy=self.memory_policy,
        )

    def _schedule_memory_consolidation_if_needed(self, session: Session) -> None:
        if len(session.messages) <= self.memory_window or session.key in self._consolidating:
            return
        self._consolidating.add(session.key)

        async def _consolidate_and_unlock() -> None:
            try:
                await self._consolidate_memory(session)
            finally:
                self._consolidating.discard(session.key)

        asyncio.create_task(_consolidate_and_unlock())
