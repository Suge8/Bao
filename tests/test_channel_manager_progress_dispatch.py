# ruff: noqa: F403, F405
from __future__ import annotations

from tests._channel_manager_progress_testkit import *


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
