# ruff: noqa: F403, F405
from __future__ import annotations

from tests._channel_manager_progress_testkit import *


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
