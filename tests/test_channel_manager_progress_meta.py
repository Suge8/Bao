# ruff: noqa: F403, F405
from __future__ import annotations

from tests._channel_manager_progress_testkit import *


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
