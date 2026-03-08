import asyncio
from collections.abc import Callable
from typing import cast

from bao.agent.loop import AgentLoop
from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels import imessage as imessage_module
from bao.channels.imessage import IMessageChannel
from bao.channels.progress_text import ProgressBuffer
from bao.config.schema import IMessageConfig
from bao.providers.base import ToolCallRequest

AUTOMATION_PERMISSION_HINT = cast(
    Callable[[str, str], str | None],
    getattr(imessage_module, "automation_permission_hint"),
)
PERMISSION_TARGET_LABEL = cast(
    Callable[[str], str],
    getattr(imessage_module, "permission_target_label"),
)


def test_permission_target_label_uses_app_name() -> None:
    assert PERMISSION_TARGET_LABEL("/Applications/Bao.app/Contents/MacOS/Bao") == "Bao"


class _FakeProc:
    def __init__(self) -> None:
        self.returncode = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", b""


def test_automation_permission_hint_detects_tcc_denial() -> None:
    result = AUTOMATION_PERMISSION_HINT(
        "51:92: execution error: 未获得授权将Apple事件发送给Messages。 (-1743)",
        "/Applications/Bao.app/Contents/MacOS/Bao",
    )

    assert result is not None
    assert "Automation" in result
    assert "Messages" in result
    assert "Bao" in result


def test_automation_permission_hint_ignores_other_errors() -> None:
    assert AUTOMATION_PERMISSION_HINT("some other osascript error", "/tmp/Bao") is None


def test_imessage_progress_flushes_before_final(monkeypatch) -> None:
    scripts: list[str] = []

    async def _fake_exec(*args, **kwargs):
        del kwargs
        scripts.append(args[2])
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    channel = IMessageChannel(IMessageConfig(enabled=True), MessageBus())

    async def _run() -> None:
        await channel.send(
            OutboundMessage(
                channel="imessage",
                chat_id="+86100",
                content="你",
                metadata={"_progress": True},
            )
        )
        await channel.send(
            OutboundMessage(
                channel="imessage",
                chat_id="+86100",
                content="好",
                metadata={"_progress": True},
            )
        )
        await channel.send(
            OutboundMessage(channel="imessage", chat_id="+86100", content="最终答案")
        )

    asyncio.run(_run())

    assert len(scripts) == 1
    assert 'send "最终答案" to targetBuddy' in scripts[0]


def test_imessage_progress_flushes_before_tool_hint(monkeypatch) -> None:
    scripts: list[str] = []

    async def _fake_exec(*args, **kwargs):
        del kwargs
        scripts.append(args[2])
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    channel = IMessageChannel(IMessageConfig(enabled=True), MessageBus())

    async def _run() -> None:
        await channel.send(
            OutboundMessage(
                channel="imessage",
                chat_id="+86100",
                content="progress",
                metadata={"_progress": True},
            )
        )
        await channel.send(
            OutboundMessage(
                channel="imessage",
                chat_id="+86100",
                content="🌐 Fetch Web Page: example.com",
                metadata={"_progress": True, "_tool_hint": True},
            )
        )

    asyncio.run(_run())

    assert len(scripts) == 2
    assert 'send "progress" to targetBuddy' in scripts[0]
    assert 'send "🌐 Fetch Web Page: example.com" to targetBuddy' in scripts[1]


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
                name="message",
                arguments={"channel": "telegram", "content": "不要暴露这段正文"},
            ),
        ],
        lang="zh",
    )

    assert hint == "💻 执行命令: uv run pytest | ✉️ 发送消息: telegram"


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


def test_tool_hint_hides_message_content_and_long_prompt_fields() -> None:
    hint = AgentLoop._tool_hint(
        [
            ToolCallRequest(
                id="t1",
                name="message",
                arguments={"content": "把这段很长很长的消息发给用户", "channel": "telegram"},
            ),
            ToolCallRequest(
                id="t2",
                name="coding_agent",
                arguments={"agent": "opencode", "prompt": "修完整个仓库里的所有问题"},
            ),
        ]
    )

    assert hint == "✉️ Send Message: telegram | 🤖 Coding Agent: opencode"


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


def test_imessage_progress_trims_initial_newlines(monkeypatch) -> None:
    scripts: list[str] = []

    async def _fake_exec(*args, **kwargs):
        del kwargs
        scripts.append(args[2])
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    channel = IMessageChannel(IMessageConfig(enabled=True), MessageBus())

    async def _run() -> None:
        await channel.send(
            OutboundMessage(
                channel="imessage",
                chat_id="+86100",
                content="\n\n杰哥，我先看看。",
                metadata={"_progress": True},
            )
        )
        await channel.send(
            OutboundMessage(
                channel="imessage",
                chat_id="+86100",
                content="",
                metadata={"_progress": True, "_tool_hint": True},
            )
        )

    asyncio.run(_run())

    assert len(scripts) == 1
    assert 'send "杰哥，我先看看。" to targetBuddy' in scripts[0]


def test_imessage_progress_waits_for_boundary_to_avoid_awkward_cut(monkeypatch) -> None:
    scripts: list[str] = []

    async def _fake_exec(*args, **kwargs):
        del kwargs
        scripts.append(args[2])
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    channel = IMessageChannel(IMessageConfig(enabled=True), MessageBus())

    async def _run() -> None:
        await channel.send(
            OutboundMessage(
                channel="imessage",
                chat_id="+86100",
                content="杰哥，我先去几个科技新闻源抓一下最近三小时的内",
                metadata={"_progress": True},
            )
        )
        assert len(scripts) == 0
        await channel.send(
            OutboundMessage(
                channel="imessage",
                chat_id="+86100",
                content="容。",
                metadata={"_progress": True},
            )
        )
        assert len(scripts) == 0
        await channel.send(
            OutboundMessage(
                channel="imessage",
                chat_id="+86100",
                content="",
                metadata={"_progress": True, "_tool_hint": True},
            )
        )
        await channel.send(OutboundMessage(channel="imessage", chat_id="+86100", content="下一步"))

    asyncio.run(_run())

    assert len(scripts) == 2
    assert 'send "杰哥，我先去几个科技新闻源抓一下最近三小时的内容。" to targetBuddy' in scripts[0]
    assert 'send "下一步" to targetBuddy' in scripts[1]


def test_imessage_progress_clear_marker_drops_buffer_without_sending(monkeypatch) -> None:
    scripts: list[str] = []

    async def _fake_exec(*args, **kwargs):
        del kwargs
        scripts.append(args[2])
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    channel = IMessageChannel(IMessageConfig(enabled=True), MessageBus())

    async def _run() -> None:
        await channel.send(
            OutboundMessage(
                channel="imessage",
                chat_id="+86100",
                content='运行这条命令静音：\nosascript -e "set volume output muted true"',
                metadata={"_progress": True},
            )
        )
        await channel.send(
            OutboundMessage(
                channel="imessage",
                chat_id="+86100",
                content="",
                metadata={"_progress": True, "_progress_clear": True},
            )
        )
        await channel.stop()

    asyncio.run(_run())

    assert scripts == []
    progress = cast(ProgressBuffer, channel._progress_handler)
    assert progress is not None
    assert progress._buf == {}
    assert progress._open == {}
    assert progress._last_text == {}
    assert progress._last_time == {}
