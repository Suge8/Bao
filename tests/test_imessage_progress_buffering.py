# ruff: noqa: F403, F405
# ruff: noqa: F403, F405
from __future__ import annotations

from tests._imessage_progress_testkit import *


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
