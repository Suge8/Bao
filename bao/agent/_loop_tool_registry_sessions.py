from __future__ import annotations

from typing import Any, Callable

from bao.agent.tools.diagnostics import RuntimeDiagnosticsTool
from bao.agent.tools.session_directory import (
    SendToSessionTool,
    SessionDefaultTool,
    SessionLookupTool,
    SessionRecentTool,
    SessionResolveTool,
    SessionStatusTool,
    SessionTranscriptTool,
)
from bao.hub import HubDirectory


def register_session_handoff_tools(
    loop: Any,
    *,
    register_tool_fn: Callable[..., None],
    options_cls: Any,
) -> None:
    directory = HubDirectory(loop.sessions)

    register_tool_fn(
        loop,
        SessionRecentTool(directory),
        options_cls(
            bundle="core",
            short_hint="List recent sendable sessions when you need a delivery target before sending.",
            aliases=("session recent", "最近会话"),
            keyword_aliases=("session", "recent", "recipient", "target", "最近会话", "收件目标"),
        ),
    )
    register_tool_fn(
        loop,
        SessionLookupTool(directory),
        options_cls(
            bundle="core",
            short_hint="Look up candidate recipients or delivery targets through the HubDirectory read-plane.",
            aliases=("session lookup", "查找会话"),
            keyword_aliases=("session", "lookup", "search", "recipient", "target", "发给谁", "查收件人"),
        ),
    )
    register_tool_fn(
        loop,
        SessionDefaultTool(directory),
        options_cls(
            bundle="core",
            short_hint="Resolve the default delivery target session through HubDirectory before sending.",
            aliases=("session default", "默认会话"),
            keyword_aliases=("session", "default", "recipient", "target", "默认目标", "收件目标"),
        ),
    )
    register_tool_fn(
        loop,
        SessionResolveTool(directory),
        options_cls(
            bundle="core",
            short_hint="Resolve a stable session_ref into a delivery target through HubDirectory.",
            aliases=("session resolve", "解析会话"),
            keyword_aliases=("session", "resolve", "session_ref", "recipient", "target", "解析目标", "会话解析"),
        ),
    )
    register_tool_fn(
        loop,
        SessionStatusTool(directory),
        options_cls(
            bundle="core",
            short_hint="Read a concise session summary for another session.",
            aliases=("session status", "会话状态"),
            keyword_aliases=("session", "status", "summary", "会话", "状态"),
        ),
    )
    register_tool_fn(
        loop,
        SessionTranscriptTool(directory),
        options_cls(
            bundle="core",
            short_hint="Read a paged session transcript via cursor/ref.",
            aliases=("session transcript", "会话记录"),
            keyword_aliases=("session", "transcript", "history", "会话", "历史"),
        ),
    )
    register_tool_fn(
        loop,
        SendToSessionTool(directory, loop.bus.publish_control),
        options_cls(
            bundle="core",
            short_hint=(
                "Hand off work to another Bao-managed session. Runtime will announce receipt on "
                "the target side and route the result back here."
            ),
            aliases=("send to session", "发到会话"),
            keyword_aliases=(
                "session",
                "send",
                "handoff",
                "profile",
                "channel",
                "会话",
                "接力",
                "转给",
                "那边处理",
            ),
        ),
    )
    register_tool_fn(
        loop,
        RuntimeDiagnosticsTool(store=loop._runtime_diagnostics),
        options_cls(
            bundle="core",
            short_hint="Inspect structured internal diagnostics when framework-side failures need explanation.",
            aliases=("runtime diagnostics", "查看诊断", "内部诊断"),
            keyword_aliases=("diagnostics", "logs", "runtime", "诊断", "内部错误"),
        ),
    )
