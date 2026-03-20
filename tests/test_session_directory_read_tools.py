from __future__ import annotations

import asyncio
import json

from bao.agent.tools.session_directory import (
    SessionDefaultTool,
    SessionLookupTool,
    SessionRecentTool,
    SessionResolveTool,
    SessionStatusTool,
    SessionTranscriptTool,
)
from bao.hub._route_resolution import SessionOrigin
from bao.hub.directory import HubDirectory
from bao.session.manager import SessionManager
from tests._session_directory_testkit import (
    DirectoryWithoutReadPlane,
    FakeDirectory,
    build_session,
    set_session_directory_context,
)


def test_session_recent_tool_returns_explicit_error_when_read_plane_missing() -> None:
    tool = SessionRecentTool(DirectoryWithoutReadPlane())
    set_session_directory_context(tool)

    result = asyncio.run(tool.execute(limit=5))

    assert result == "Error: session discovery read-plane not available yet."


def test_session_lookup_default_and_resolve_tools_forward_to_directory() -> None:
    directory = FakeDirectory()
    recent = SessionRecentTool(directory)
    lookup = SessionLookupTool(directory)
    default = SessionDefaultTool(directory)
    resolve = SessionResolveTool(directory)
    for tool in (recent, lookup, default, resolve):
        set_session_directory_context(tool)

    recent_payload = json.loads(asyncio.run(recent.execute(limit=3)))
    lookup_payload = json.loads(asyncio.run(lookup.execute(query="alice", limit=2, channel="telegram")))
    default_payload = json.loads(asyncio.run(default.execute(channel="telegram", scope="profile:work")))
    resolve_payload = json.loads(asyncio.run(resolve.execute(session_ref="sess_abc")))

    assert recent_payload == [{"session_key": "desktop:local::a", "limit": 3}]
    assert lookup_payload == [{"query": "alice", "limit": 2, "channel": "telegram"}]
    assert default_payload == {
        "channel": "telegram",
        "scope": "profile:work",
        "session_key": "desktop:local::current",
    }
    assert resolve_payload["session_ref"] == "sess_abc"
    assert resolve_payload["session_key"] == "desktop:local::target"


def test_session_status_and_transcript_tools_use_compact_read_surface() -> None:
    directory = FakeDirectory()
    status = SessionStatusTool(directory)
    transcript = SessionTranscriptTool(directory)
    for tool in (status, transcript):
        set_session_directory_context(tool)

    status_payload = json.loads(asyncio.run(status.execute(session_ref="sess_abc")))
    transcript_payload = json.loads(
        asyncio.run(
            transcript.execute(
                session_ref="sess_abc",
                mode="tail",
                limit=5,
                cursor="cur-1",
                transcript_ref="ref-1",
            )
        )
    )

    assert status_payload == {
        "key": "desktop:local::target",
        "ref": "sess_abc",
        "title": "Target Session",
        "channel": "desktop",
        "state": "active",
        "updated_at": "2026-03-19T10:00:00Z",
        "msgs": 3,
        "has_msgs": True,
        "identity": "ident:test",
        "binding": "channel=desktop|peer=local",
    }
    assert transcript_payload == {
        "key": "desktop:local::target",
        "ref": "sess_abc",
        "mode": "tail",
        "tx": "ref-1",
        "total": 3,
        "start": 1,
        "end": 3,
        "items": [{"role": "assistant", "content": "hello"}],
        "prev": "prev-1",
        "next": "",
        "more_before": True,
        "more_after": False,
    }


def test_session_transcript_tool_supports_raw_rows() -> None:
    tool = SessionTranscriptTool(FakeDirectory())
    set_session_directory_context(tool)

    payload = json.loads(asyncio.run(tool.execute(session_key="desktop:local::target", raw=True)))

    assert payload["items"] == [{"role": "assistant", "content": "hello", "timestamp": "ignored"}]


def test_session_transcript_tool_returns_explicit_ref_mismatch() -> None:
    tool = SessionTranscriptTool(FakeDirectory())
    set_session_directory_context(tool)

    result = asyncio.run(tool.execute(session_key="desktop:local::target", transcript_ref="bad-ref"))

    assert result == "Error: transcript_ref_mismatch"


def test_session_directory_tools_use_real_hub_directory_read_plane(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    directory = HubDirectory(manager)
    desktop_key = "desktop:local::main"
    telegram_key = "telegram:-100123:topic:42::thread"
    build_session(manager, desktop_key, [("user", "desktop")])
    build_session(manager, telegram_key, [("assistant", "telegram")])
    directory.observe_origin(
        desktop_key,
        SessionOrigin(channel="desktop", peer_id="local"),
    )
    directory.observe_origin(
        telegram_key,
        SessionOrigin(channel="telegram", peer_id="-100123", thread_id="42"),
    )

    recent_tool = SessionRecentTool(directory)
    lookup_tool = SessionLookupTool(directory)
    default_tool = SessionDefaultTool(directory)
    resolve_tool = SessionResolveTool(directory)
    status_tool = SessionStatusTool(directory)
    transcript_tool = SessionTranscriptTool(directory)
    for tool in (
        recent_tool,
        lookup_tool,
        default_tool,
        resolve_tool,
        status_tool,
        transcript_tool,
    ):
        set_session_directory_context(tool)

    recent_payload = json.loads(asyncio.run(recent_tool.execute(limit=4)))
    lookup_payload = json.loads(asyncio.run(lookup_tool.execute(query="telegram", channel="telegram")))
    default_payload = json.loads(asyncio.run(default_tool.execute(channel="telegram")))
    session_ref = lookup_payload[0]["session_ref"]
    resolve_payload = json.loads(asyncio.run(resolve_tool.execute(session_ref=session_ref)))
    status_payload = json.loads(asyncio.run(status_tool.execute(session_ref=session_ref)))
    transcript_payload = json.loads(asyncio.run(transcript_tool.execute(session_ref=session_ref, mode="tail", limit=5)))

    assert [item["session_key"] for item in recent_payload] == [telegram_key, desktop_key]
    assert lookup_payload[0]["sendable"] is True
    assert lookup_payload[0]["delivery_channel"] == "telegram"
    assert lookup_payload[0]["delivery_chat_id"] == "-100123"
    assert lookup_payload[0]["delivery_metadata"] == {"message_thread_id": "42"}
    assert default_payload["session_key"] == telegram_key
    assert resolve_payload["session_key"] == telegram_key
    assert resolve_payload["session_ref"] == session_ref
    assert status_payload["channel"] == "telegram"
    assert transcript_payload["items"][0]["content"] == "telegram"
