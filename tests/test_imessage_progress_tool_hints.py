# ruff: noqa: F403, F405
# ruff: noqa: F403, F405
from __future__ import annotations

from tests._imessage_progress_testkit import *


def test_tool_hint_url_keeps_readable_path() -> None:
    hint = AgentLoop._tool_hint(
        [
            ToolCallRequest(
                id="t1",
                name="web_fetch",
                arguments={
                    "url": "https://www.theverge.com/ai-artificial-intelligence/2026/2/25/demo"
                },
            )
        ]
    )

    assert "🌐 Fetch Web Page: theverge.com/ai-artificial-intelligence/.../demo" == hint


def test_tool_hint_handles_list_type_arguments() -> None:
    class _ListArgsToolCall:
        name = "web_search"
        arguments = [{"query": "latest ai news"}]

    hint = AgentLoop._tool_hint([_ListArgsToolCall()])
    assert hint == "🔎 Search Web: latest ai news"


def test_tool_hint_maps_internal_names_to_friendly_labels() -> None:
    hint = AgentLoop._tool_hint(
        [
            ToolCallRequest(id="t1", name="read_file", arguments={"path": "bao/agent/loop.py"}),
            ToolCallRequest(id="t2", name="create_plan", arguments={}),
            ToolCallRequest(id="t3", name="github__list_issues", arguments={"repo": "foo/bar"}),
        ]
    )

    assert hint == ("📄 Read File: bao/agent/loop.py | 🗂️ Create Plan | 📁 List Issues: foo/bar")


def test_tool_hint_prefers_safe_spawn_label_over_long_task_prompt() -> None:
    hint = AgentLoop._tool_hint(
        [
            ToolCallRequest(
                id="t1",
                name="spawn",
                arguments={
                    "task": "目标：启动一个最小可验证的子代理任务用于连通性测试。范围：仅执行一个简单动作并返回明确完成结果。",
                    "label": "连通性测试",
                },
            )
        ]
    )

    assert hint == "🤖 Delegate Task: 连通性测试"


def test_tool_hint_localizes_labels_for_zh_sessions() -> None:
    hint = AgentLoop._tool_hint(
        [
            ToolCallRequest(id="t1", name="web_search", arguments={"query": "latest ai news"}),
            ToolCallRequest(
                id="t2", name="spawn", arguments={"label": "连通性测试", "task": "长任务"}
            ),
            ToolCallRequest(id="t3", name="update_plan_step", arguments={"step_index": 2}),
        ],
        lang="zh",
    )

    assert hint == "🔎 搜索网页: latest ai news | 🤖 委派任务: 连通性测试 | 🗂️ 更新计划: 第2步"


def test_tool_hint_localizes_exec_and_message_labels_for_zh_sessions() -> None:
    hint = AgentLoop._tool_hint(
        [
            ToolCallRequest(
                id="t1",
                name="exec",
                arguments={"command": "DEBUG=1 uv run pytest tests/test_chat_service.py -q"},
            ),
            ToolCallRequest(
                id="t2",
                name="send_to_session",
                arguments={"session_ref": "sess_tg", "content": "不要暴露这段正文"},
            ),
        ],
        lang="zh",
    )

    assert hint == "💻 执行命令: uv run pytest | 📨 发到会话: sess_tg · 不要暴露这段正文"


def test_tool_hint_localizes_cron_actions_for_zh_sessions() -> None:
    hint = AgentLoop._tool_hint(
        [
            ToolCallRequest(id="t1", name="cron", arguments={"action": "add"}),
            ToolCallRequest(id="t2", name="cron", arguments={"action": "list"}),
            ToolCallRequest(id="t3", name="cron", arguments={"action": "remove"}),
        ],
        lang="zh",
    )

    assert hint == "⏰ 安排任务: 新增 | ⏰ 安排任务: 查看 | ⏰ 安排任务: 删除"


def test_tool_hint_covers_backend_specific_agent_names() -> None:
    zh_hint = AgentLoop._tool_hint(
        [
            ToolCallRequest(id="t1", name="opencode", arguments={"prompt": "do work"}),
            ToolCallRequest(id="t2", name="codex_details", arguments={"session_id": "abc123"}),
            ToolCallRequest(id="t3", name="claudecode", arguments={"prompt": "review"}),
        ],
        lang="zh",
    )
    en_hint = AgentLoop._tool_hint(
        [
            ToolCallRequest(id="t1", name="opencode", arguments={"prompt": "do work"}),
            ToolCallRequest(id="t2", name="codex_details", arguments={"session_id": "abc123"}),
            ToolCallRequest(id="t3", name="claudecode", arguments={"prompt": "review"}),
        ],
        lang="en",
    )

    assert zh_hint == "🤖 OpenCode 代理 | 🤖 Codex 详情: abc123 | 🤖 Claude Code 代理"
    assert en_hint == "🤖 OpenCode Agent | 🤖 Codex Details: abc123 | 🤖 Claude Code Agent"


def test_tool_hint_previews_message_content_and_hides_long_prompt_fields() -> None:
    hint = AgentLoop._tool_hint(
        [
            ToolCallRequest(
                id="t1",
                name="send_to_session",
                arguments={
                    "content": "把这段很长很长的消息发给用户",
                    "session_key": "telegram:6374137703::s4",
                },
            ),
            ToolCallRequest(
                id="t2",
                name="coding_agent",
                arguments={"agent": "opencode", "prompt": "修完整个仓库里的所有问题"},
            ),
        ]
    )

    assert hint == "📨 Send To Session: telegram:6374137703::s4 · 把这段很长很长的消息发给用户 | 🤖 Coding Agent: opencode"


def test_tool_hint_summarizes_exec_command_briefly() -> None:
    hint = AgentLoop._tool_hint(
        [
            ToolCallRequest(
                id="t1",
                name="exec",
                arguments={
                    "command": "DEBUG=1 PYTHONPATH=. uv run pytest tests/test_chat_service.py -q && echo done"
                },
            )
        ]
    )

    assert hint == "💻 Run Command: uv run pytest"
