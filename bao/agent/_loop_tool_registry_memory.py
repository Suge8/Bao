from __future__ import annotations

from typing import Any, cast

from bao.agent.tools.cron import CronTool
from bao.agent.tools.memory import ForgetTool, RememberTool, UpdateMemoryTool

from ._loop_tool_registry_common import ToolRegistrationOptions, register_tool


def register_memory_and_cron_tools(loop: Any) -> None:
    memory = cast(Any, loop.context.memory)
    _register_memory_tools(loop, memory)
    _register_cron_tool(loop)


def _register_memory_tools(loop: Any, memory: Any) -> None:
    register_tool(
        loop,
        RememberTool(memory=memory),
        ToolRegistrationOptions(
            bundle="core",
            short_hint="Write an explicit fact into long-term memory.",
            aliases=("remember", "记住"),
            keyword_aliases=("memory", "remember", "记忆", "记住"),
        ),
    )
    register_tool(
        loop,
        ForgetTool(memory=memory),
        ToolRegistrationOptions(
            bundle="core",
            short_hint="Delete memory entries that match a query.",
            aliases=("forget", "忘记", "删除记忆"),
            keyword_aliases=("memory", "forget", "删除记忆"),
        ),
    )
    register_tool(
        loop,
        UpdateMemoryTool(memory=memory),
        ToolRegistrationOptions(
            bundle="core",
            short_hint="Replace the content of one memory category.",
            aliases=("update memory", "更新记忆"),
            keyword_aliases=("memory", "update", "更新记忆"),
        ),
    )


def _register_cron_tool(loop: Any) -> None:
    if loop.cron_service:
        register_tool(
            loop,
            CronTool(loop.cron_service),
            ToolRegistrationOptions(
                bundle="core",
                short_hint="Schedule reminders and recurring tasks.",
                aliases=("cron", "reminder", "提醒", "定时"),
                keyword_aliases=("schedule", "cron", "remind", "提醒", "定时"),
            ),
        )
