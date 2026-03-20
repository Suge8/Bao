from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bao.agent import plan as plan_state
from bao.agent.reply_route import normalize_reply_metadata
from bao.agent.tools.agent_browser import AgentBrowserTool
from bao.agent.tools.cron import CronTool
from bao.agent.tools.session_directory import (
    SendToSessionTool,
    SessionDefaultTool,
    SessionDirectoryToolContext,
    SessionLookupTool,
    SessionRecentTool,
    SessionResolveTool,
    SessionStatusTool,
    SessionTranscriptTool,
)
from bao.agent.tools.spawn import SpawnTool
from bao.agent.tools.web import WebFetchTool


@dataclass(frozen=True, slots=True)
class ToolContextRequest:
    channel: str
    chat_id: str
    session_key: str | None = None
    lang: str | None = None
    metadata: dict[str, Any] | None = None


def set_tool_context(loop: Any, request: ToolContextRequest) -> None:
    preferred_lang = (
        plan_state.normalize_language(request.lang)
        if isinstance(request.lang, str)
        else loop._resolve_user_language()
    )
    reply_metadata = normalize_reply_metadata(request.metadata)
    _set_session_directory_context(loop, request, preferred_lang, reply_metadata)
    _set_spawn_context(loop, request, preferred_lang, reply_metadata)
    _set_direct_tool_contexts(loop, request)
    _set_plan_tool_contexts(loop, request, preferred_lang, reply_metadata)


def _set_spawn_context(
    loop: Any,
    request: ToolContextRequest,
    preferred_lang: str,
    reply_metadata: dict[str, Any],
) -> None:
    tool = loop.tools.get("spawn")
    if isinstance(tool, SpawnTool):
        tool.set_context(
            request.channel,
            request.chat_id,
            session_key=request.session_key,
            lang=preferred_lang,
            reply_metadata=reply_metadata,
        )


def _set_session_directory_context(
    loop: Any,
    request: ToolContextRequest,
    preferred_lang: str,
    reply_metadata: dict[str, Any],
) -> None:
    context = SessionDirectoryToolContext(
        channel=request.channel,
        chat_id=request.chat_id,
        session_key=request.session_key,
        lang=preferred_lang,
        message_id=_resolve_session_directory_message_id(request.metadata),
        reply_metadata=reply_metadata,
    )
    for name, tool_type in (
        ("session_recent", SessionRecentTool),
        ("session_lookup", SessionLookupTool),
        ("session_default", SessionDefaultTool),
        ("session_resolve", SessionResolveTool),
        ("session_status", SessionStatusTool),
        ("session_transcript", SessionTranscriptTool),
        ("send_to_session", SendToSessionTool),
    ):
        tool = loop.tools.get(name)
        if isinstance(tool, tool_type):
            tool.set_context(context)


def _resolve_session_directory_message_id(
    metadata: dict[str, Any] | None,
) -> str | int | None:
    if not isinstance(metadata, dict):
        return None
    for key in ("reply_to", "message_id"):
        value = metadata.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _set_direct_tool_contexts(loop: Any, request: ToolContextRequest) -> None:
    cron_tool = loop.tools.get("cron")
    if isinstance(cron_tool, CronTool):
        cron_tool.set_context(request.channel, request.chat_id)
    web_fetch_tool = loop.tools.get("web_fetch")
    if isinstance(web_fetch_tool, WebFetchTool):
        web_fetch_tool.set_context(
            request.channel,
            request.chat_id,
            session_key=request.session_key,
        )
    browser_tool = loop.tools.get("agent_browser")
    if isinstance(browser_tool, AgentBrowserTool):
        browser_tool.set_context(
            request.channel,
            request.chat_id,
            session_key=request.session_key,
        )
    for name in ("coding_agent", "coding_agent_details"):
        tool = loop.tools.get(name)
        set_context_fn = getattr(tool, "set_context", None)
        if callable(set_context_fn):
            set_context_fn(request.channel, request.chat_id, session_key=request.session_key)


def _set_plan_tool_contexts(
    loop: Any,
    request: ToolContextRequest,
    preferred_lang: str,
    reply_metadata: dict[str, Any],
) -> None:
    for name in ("create_plan", "update_plan_step", "clear_plan"):
        tool = loop.tools.get(name)
        set_context_fn = getattr(tool, "set_context", None)
        if callable(set_context_fn):
            set_context_fn(
                request.channel,
                request.chat_id,
                session_key=request.session_key,
                lang=preferred_lang,
                reply_metadata=reply_metadata,
            )
