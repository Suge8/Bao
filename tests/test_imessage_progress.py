import asyncio

from bao.agent.loop import AgentLoop
from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels.imessage import IMessageChannel
from bao.config.schema import IMessageConfig
from bao.providers.base import ToolCallRequest


class _FakeProc:
    def __init__(self) -> None:
        self.returncode = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", b""


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
                content='web_fetch("https://example.com")',
                metadata={"_progress": True, "_tool_hint": True},
            )
        )

    asyncio.run(_run())

    assert len(scripts) == 2
    assert 'send "progress" to targetBuddy' in scripts[0]
    assert 'send "web_fetch(\\"https://example.com\\")" to targetBuddy' in scripts[1]


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

    assert 'web_fetch("https://www.theverge.com/ai-artificial-intelligence/.../demo")' == hint


def test_tool_hint_handles_list_type_arguments() -> None:
    class _ListArgsToolCall:
        name = "web_search"
        arguments = [{"query": "latest ai news"}]

    hint = AgentLoop._tool_hint([_ListArgsToolCall()])
    assert hint == 'web_search("latest ai news")'


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
    assert channel._progress._buf == {}
    assert channel._progress._open == {}
    assert channel._progress._last_text == {}
    assert channel._progress._last_time == {}
