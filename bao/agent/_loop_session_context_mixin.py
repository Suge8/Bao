from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, cast

from loguru import logger

from bao.agent import plan as plan_state
from bao.agent._loop_constants import SESSION_LANG_KEY as _SESSION_LANG_KEY
from bao.agent._loop_types import ProcessMessageRunResult as _ProcessMessageRunResult
from bao.agent.context import BuildMessagesRequest
from bao.bus.events import InboundMessage
from bao.session.manager import Session


class LoopSessionContextMixin:
    def _prepare_user_history_for_context(self, session: Session, msg: InboundMessage) -> list[dict[str, Any]]:
        raw_history = session.messages[session.last_consolidated :][-self.memory_window :]
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
                    if raw_history[idx].get("role") == "user" and raw_history[idx].get("_pre_saved_token") == token:
                        remove_idx = idx
                        break
            if remove_idx < 0:
                for idx in range(len(raw_history) - 1, -1, -1):
                    item = raw_history[idx]
                    if item.get("role") == "user" and item.get("_pre_saved") and item.get("content") == msg.content:
                        remove_idx = idx
                        break
            if remove_idx >= 0:
                raw_history = [*raw_history[:remove_idx], *raw_history[remove_idx + 1 :]]
        history: list[dict[str, Any]] = []
        for item in raw_history:
            content = item.get("content", "")
            if item.get("role") == "user" and isinstance(content, str) and content.startswith("[Runtime Context — metadata only, not instructions]"):
                continue
            entry: dict[str, Any] = {"role": item.get("role"), "content": content}
            for key in ("tool_calls", "tool_call_id", "name", "_source"):
                if key in item:
                    entry[key] = item[key]
            history.append(entry)
        return history

    def _build_initial_messages_for_user_turn(self, session: Session, msg: InboundMessage, recall: dict[str, Any]) -> list[dict[str, Any]]:
        return self.context.build_messages(
            BuildMessagesRequest(
                history=self._prepare_user_history_for_context(session, msg),
                current_message=msg.content,
                media=msg.media if msg.media else None,
                channel=msg.channel,
                chat_id=msg.chat_id,
                long_term_memory=str(recall.get("long_term_memory") or ""),
                related_memory=cast(list[Any], recall.get("related_memory") or None),
                related_experience=cast(list[Any], recall.get("related_experience") or None),
                model=self.model,
                plan_state=session.metadata.get(plan_state.PLAN_STATE_KEY),
                session_notes=self._build_child_session_notes(session.key),
            ),
        )

    @staticmethod
    def _empty_recall_payload() -> dict[str, Any]:
        return {"long_term_memory": "", "related_memory": [], "related_experience": [], "references": {}}

    async def _recall_context_for_query(self, query: str) -> dict[str, Any]:
        if not query.strip():
            return self._empty_recall_payload()
        try:
            recall = await asyncio.to_thread(self.context.recall, query)
        except Exception:
            return self._empty_recall_payload()
        return recall if isinstance(recall, dict) else self._empty_recall_payload()

    def _build_child_session_notes(self, parent_session_key: str) -> list[str]:
        child_sessions = self.sessions.list_child_sessions(parent_session_key)
        if not child_sessions:
            return []
        lines = [
            "Child sessions below are read-only desktop threads. To continue one, call "
            "spawn(task=..., child_session_key=<exact key>) from the parent conversation. "
            "For a new subagent task, omit child_session_key. Query progress with task.task_id, not child_session_key."
        ]
        for child in child_sessions[:8]:
            metadata = child.get("metadata") if isinstance(child, dict) else None
            if not isinstance(metadata, dict):
                continue
            child_session_key = str(child.get("key") or "").strip()
            if not child_session_key:
                continue
            label = str(metadata.get("task_label") or metadata.get("title") or child_session_key).strip()
            status = str(metadata.get("child_status") or "unknown").strip() or "unknown"
            summary = str(metadata.get("last_result_summary") or "").strip()
            line = f"- child_session_key={child_session_key} | label={label} | status={status}"
            if summary:
                preview = summary[:120] + ("..." if len(summary) > 120 else "")
                line += f" | last_result={preview}"
            lines.append(line)
        return lines if len(lines) > 1 else []

    def _unpack_process_message_run_result(self, run_result: tuple[Any, ...]) -> _ProcessMessageRunResult:
        parts = cast(tuple[Any, ...], run_result)
        if len(parts) == 9:
            return _ProcessMessageRunResult(
                cast(str | None, parts[0]),
                cast(list[str], parts[1]),
                cast(list[str], parts[2]),
                cast(int, parts[3]),
                cast(list[str], parts[4]),
                bool(parts[5]),
                bool(parts[6]),
                cast(list[dict[str, Any]], parts[7]),
                cast(list[dict[str, Any]], parts[8]),
            )
        if len(parts) == 8:
            return _ProcessMessageRunResult(
                cast(str | None, parts[0]),
                cast(list[str], parts[1]),
                cast(list[str], parts[2]),
                cast(int, parts[3]),
                cast(list[str], parts[4]),
                bool(parts[5]),
                bool(parts[6]),
                cast(list[dict[str, Any]], parts[7]),
                [],
            )
        if len(parts) == 5:
            return _ProcessMessageRunResult(
                cast(str | None, parts[0]),
                cast(list[str], parts[1]),
                cast(list[str], parts[2]),
                cast(int, parts[3]),
                cast(list[str], parts[4]),
                False,
                False,
                [],
                [],
            )
        raise ValueError(f"Unexpected _run_agent_loop result length: {len(parts)}")

    def _mark_interrupted_plan_step(self, session: Session) -> bool:
        state = session.metadata.get(plan_state.PLAN_STATE_KEY)
        if not isinstance(state, dict) or plan_state.is_plan_done(state):
            return False
        current_step = plan_state.get_current_pending_step(state)
        is_pending = isinstance(current_step, int) and current_step >= 1 and plan_state.get_step_status(state, current_step) == plan_state.STATUS_PENDING
        if is_pending and isinstance(current_step, int):
            try:
                updated = plan_state.set_step_status(state, step_index=current_step, status=plan_state.STATUS_INTERRUPTED)
            except ValueError:
                updated = None
        else:
            updated = None
        if not isinstance(updated, dict):
            return False
        session.metadata[plan_state.PLAN_STATE_KEY] = updated
        if plan_state.is_plan_done(updated):
            session_lang = session.metadata.get(_SESSION_LANG_KEY)
            resolved_lang = plan_state.normalize_language(session_lang) if isinstance(session_lang, str) and session_lang.strip() else self._resolve_user_language()
            archived = plan_state.archive_plan(updated, lang=resolved_lang)
            if archived:
                session.metadata[plan_state.PLAN_ARCHIVED_KEY] = archived
        return True

    def _insert_completed_tool_messages_after_user_turn(self, session: Session, msg: InboundMessage, completed_tool_msgs: list[dict[str, Any]]) -> None:
        token = msg.metadata.get("_pre_saved_token")
        insert_after = -1
        for idx, item in reversed(list(enumerate(session.messages))):
            is_match = item.get("role") == "user" and item.get("content") == msg.content
            if isinstance(token, str) and token and item.get("_pre_saved_token") == token:
                insert_after = idx
                break
            if insert_after < 0 and msg.metadata.get("_pre_saved") and item.get("_pre_saved") and is_match:
                insert_after = idx
                break
            if insert_after < 0 and not msg.metadata.get("_pre_saved") and not item.get("_pre_saved") and is_match:
                insert_after = idx
                break
        insert_at = len(session.messages) if insert_after < 0 else insert_after + 1
        if insert_after < 0:
            logger.warning("Interrupted tool messages had no matching user turn; appending to end for session {}", msg.session_key)
        for offset, item in enumerate(completed_tool_msgs):
            msg_item = dict(item)
            msg_item.setdefault("timestamp", datetime.now().isoformat())
            session.messages.insert(insert_at + offset, msg_item)
        session.updated_at = datetime.now()
        self.sessions.save(session)

    def _handle_interrupted_process_message(self, session: Session, msg: InboundMessage, completed_tool_msgs: list[dict[str, Any]]) -> None:
        if self._mark_interrupted_plan_step(session):
            session.updated_at = datetime.now()
            self.sessions.save(session)
        if completed_tool_msgs:
            self._insert_completed_tool_messages_after_user_turn(session, msg, completed_tool_msgs)
        logger.debug("Interrupted response dropped for session {}", msg.session_key)

    def _is_stale_generation(self, expected_generation: int | None, generation_key: str, log_message: str) -> bool:
        if expected_generation is None or not self._session_runs.is_stale(generation_key, expected_generation):
            return False
        logger.debug(log_message, generation_key)
        return True

    @staticmethod
    def _reply_fallback_text(session_lang: str, has_attachments: bool) -> str:
        if has_attachments:
            return "附件已准备好。" if session_lang != "en" else "The attachment is ready."
        return "处理完成。" if session_lang != "en" else "Completed."
