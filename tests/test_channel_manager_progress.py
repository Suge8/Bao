import asyncio
import json
from contextlib import suppress

import pytest

from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.channels.manager import ChannelManager
from bao.config.schema import Config, IMessageConfig


class _DummyChannel(BaseChannel):
    name = "dummy"

    def __init__(self, bus: MessageBus):
        super().__init__(IMessageConfig(enabled=True), bus)
        self.sent: list[OutboundMessage] = []

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        self.sent.append(msg)


class _DummyProgressHandler:
    async def handle(self, *_args, **_kwargs) -> None:
        return None

    async def flush(self, *_args, **_kwargs) -> None:
        return None

    def clear_all(self) -> None:
        return None


class _FailingStartChannel(_DummyChannel):
    async def start(self) -> None:
        raise RuntimeError("boom-start")


class _FailingSendChannel(_DummyChannel):
    async def send(self, msg: OutboundMessage) -> None:
        _ = msg
        raise RuntimeError("boom-send")


def _dispatch_one(
    manager: ChannelManager, bus: MessageBus, msg: OutboundMessage, channel: _DummyChannel
) -> None:
    async def _run() -> None:
        task = asyncio.create_task(manager._dispatch_outbound())
        try:
            await bus.publish_outbound(msg)
            for _ in range(20):
                if channel.sent:
                    break
                await asyncio.sleep(0.01)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    asyncio.run(_run())


def test_tool_hint_suppressed_keeps_iteration_boundary() -> None:
    bus = MessageBus()
    cfg = Config()
    cfg.agents.defaults.send_progress = True
    cfg.agents.defaults.send_tool_hints = False

    manager = ChannelManager(cfg, bus)
    dummy = _DummyChannel(bus)
    dummy._progress_handler = _DummyProgressHandler()
    manager.channels = {"dummy": dummy}

    _dispatch_one(
        manager,
        bus,
        OutboundMessage(
            channel="dummy",
            chat_id="c1",
            content='web_fetch("https://example.com")',
            metadata={"_progress": True, "_tool_hint": True, "_progress_kind": "tool"},
        ),
        dummy,
    )

    assert len(dummy.sent) == 1
    sent = dummy.sent[0]
    assert sent.content == ""
    assert sent.metadata.get("_tool_hint") is True
    assert sent.metadata.get("_tool_hint_suppressed") is True


@pytest.mark.asyncio
async def test_stop_all_cancels_idle_dispatcher() -> None:
    bus = MessageBus()
    cfg = Config()
    manager = ChannelManager(cfg, bus)
    manager.channels = {"dummy": _DummyChannel(bus)}
    manager._dispatch_task = asyncio.create_task(manager._dispatch_outbound())

    await asyncio.sleep(0)
    await manager.stop_all()

    dispatch_task = manager._dispatch_task
    assert dispatch_task is not None and dispatch_task.done()


def test_tool_hints_enabled_by_default() -> None:
    cfg = Config()

    assert cfg.agents.defaults.send_tool_hints is True


def test_tool_hint_dropped_when_progress_also_disabled() -> None:
    bus = MessageBus()
    cfg = Config()
    cfg.agents.defaults.send_progress = False
    cfg.agents.defaults.send_tool_hints = False

    manager = ChannelManager(cfg, bus)
    dummy = _DummyChannel(bus)
    manager.channels = {"dummy": dummy}

    _dispatch_one(
        manager,
        bus,
        OutboundMessage(
            channel="dummy",
            chat_id="c2",
            content='web_fetch("https://example.com")',
            metadata={"_progress": True, "_tool_hint": True, "_progress_kind": "tool"},
        ),
        dummy,
    )

    assert dummy.sent == []


def test_progress_dropped_for_channels_without_progress_handler() -> None:
    bus = MessageBus()
    cfg = Config()
    cfg.agents.defaults.send_progress = True

    manager = ChannelManager(cfg, bus)
    dummy = _DummyChannel(bus)
    manager.channels = {"dummy": dummy}

    _dispatch_one(
        manager,
        bus,
        OutboundMessage(
            channel="dummy",
            chat_id="c-progress",
            content="流式增量",
            metadata={"_progress": True},
        ),
        dummy,
    )

    assert dummy.sent == []


def test_opencode_meta_transformed_to_status_line() -> None:
    bus = MessageBus()
    cfg = Config()
    manager = ChannelManager(cfg, bus)
    dummy = _DummyChannel(bus)
    manager.channels = {"dummy": dummy}

    raw_meta = {
        "status": "success",
        "attempts": 1,
        "duration_ms": 1250,
        "session_id": "sess-1",
    }
    content = (
        "OpenCode completed successfully.\n\n"
        + "OPENCODE_META="
        + json.dumps(raw_meta, ensure_ascii=False)
        + "\n\nSummary:\nDone"
    )

    _dispatch_one(
        manager,
        bus,
        OutboundMessage(channel="dummy", chat_id="c3", content=content, metadata={}),
        dummy,
    )

    assert len(dummy.sent) == 1
    sent = dummy.sent[0]
    assert sent.content.startswith("✅ OpenCode status: success")
    assert "OPENCODE_META=" not in sent.content
    assert sent.metadata.get("_opencode_status") == "success"
    assert sent.metadata.get("_opencode_meta", {}).get("session_id") == "sess-1"


def test_invalid_opencode_meta_is_left_unchanged() -> None:
    bus = MessageBus()
    cfg = Config()
    manager = ChannelManager(cfg, bus)
    dummy = _DummyChannel(bus)
    manager.channels = {"dummy": dummy}

    content = "OPENCODE_META={bad json}\n\nSummary:\nDone"
    _dispatch_one(
        manager,
        bus,
        OutboundMessage(channel="dummy", chat_id="c4", content=content, metadata={}),
        dummy,
    )

    assert len(dummy.sent) == 1
    sent = dummy.sent[0]
    assert sent.content == content
    assert "_opencode_meta" not in sent.metadata


def test_codex_meta_transformed_to_status_line() -> None:
    bus = MessageBus()
    cfg = Config()
    manager = ChannelManager(cfg, bus)
    dummy = _DummyChannel(bus)
    manager.channels = {"dummy": dummy}

    raw_meta = {
        "status": "success",
        "attempts": 2,
        "duration_ms": 950,
        "session_id": "sess-codex-1",
    }
    content = (
        "Codex completed successfully.\n\n"
        + "CODEX_META="
        + json.dumps(raw_meta, ensure_ascii=False)
        + "\n\nSummary:\nDone"
    )

    _dispatch_one(
        manager,
        bus,
        OutboundMessage(channel="dummy", chat_id="c5", content=content, metadata={}),
        dummy,
    )

    assert len(dummy.sent) == 1
    sent = dummy.sent[0]
    assert sent.content.startswith("✅ Codex status: success")
    assert "CODEX_META=" not in sent.content
    assert sent.metadata.get("_codex_status") == "success"
    assert sent.metadata.get("_codex_meta", {}).get("session_id") == "sess-codex-1"


def test_invalid_codex_meta_is_left_unchanged() -> None:
    bus = MessageBus()
    cfg = Config()
    manager = ChannelManager(cfg, bus)
    dummy = _DummyChannel(bus)
    manager.channels = {"dummy": dummy}

    content = "CODEX_META={bad json}\n\nSummary:\nDone"
    _dispatch_one(
        manager,
        bus,
        OutboundMessage(channel="dummy", chat_id="c6", content=content, metadata={}),
        dummy,
    )

    assert len(dummy.sent) == 1
    sent = dummy.sent[0]
    assert sent.content == content
    assert "_codex_meta" not in sent.metadata


def test_claudecode_meta_transformed_to_status_line() -> None:
    bus = MessageBus()
    cfg = Config()
    manager = ChannelManager(cfg, bus)
    dummy = _DummyChannel(bus)
    manager.channels = {"dummy": dummy}

    raw_meta = {
        "status": "success",
        "attempts": 1,
        "duration_ms": 860,
        "session_id": "sess-claude-1",
    }
    content = (
        "Claude Code completed successfully.\n\n"
        + "CLAUDECODE_META="
        + json.dumps(raw_meta, ensure_ascii=False)
        + "\n\nSummary:\nDone"
    )

    _dispatch_one(
        manager,
        bus,
        OutboundMessage(channel="dummy", chat_id="c7", content=content, metadata={}),
        dummy,
    )

    assert len(dummy.sent) == 1
    sent = dummy.sent[0]
    assert sent.content.startswith("✅ Claude Code status: success")
    assert "CLAUDECODE_META=" not in sent.content
    assert sent.metadata.get("_claudecode_status") == "success"
    assert sent.metadata.get("_claudecode_meta", {}).get("session_id") == "sess-claude-1"


def test_invalid_claudecode_meta_is_left_unchanged() -> None:
    bus = MessageBus()
    cfg = Config()
    manager = ChannelManager(cfg, bus)
    dummy = _DummyChannel(bus)
    manager.channels = {"dummy": dummy}

    content = "CLAUDECODE_META={bad json}\n\nSummary:\nDone"
    _dispatch_one(
        manager,
        bus,
        OutboundMessage(channel="dummy", chat_id="c8", content=content, metadata={}),
        dummy,
    )

    assert len(dummy.sent) == 1
    sent = dummy.sent[0]
    assert sent.content == content
    assert "_claudecode_meta" not in sent.metadata


def test_channel_start_failure_reports_callback() -> None:
    bus = MessageBus()
    cfg = Config()
    reported: list[tuple[str, str, str]] = []
    manager = ChannelManager(
        cfg,
        bus,
        on_channel_error=lambda stage, name, detail: reported.append((stage, name, detail)),
    )

    asyncio.run(manager._start_channel("telegram", _FailingStartChannel(bus)))

    assert reported == [("start_failed", "telegram", "boom-start")]


def test_channel_send_failure_reports_callback() -> None:
    bus = MessageBus()
    cfg = Config()
    reported: list[tuple[str, str, str]] = []
    manager = ChannelManager(
        cfg,
        bus,
        on_channel_error=lambda stage, name, detail: reported.append((stage, name, detail)),
    )
    failing = _FailingSendChannel(bus)
    manager.channels = {"telegram": failing}

    _dispatch_one(
        manager,
        bus,
        OutboundMessage(channel="telegram", chat_id="c-send", content="hello", metadata={}),
        failing,
    )

    assert reported == [("send_failed", "telegram", "boom-send")]
