from __future__ import annotations

import asyncio
import json

from bao.agent.tools.session_directory import SessionDirectoryToolContext
from bao.bus.events import ControlEvent
from bao.hub import TranscriptPage
from bao.session.manager import SessionManager


class DirectoryWithoutReadPlane:
    pass


class FakeDirectory:
    def list_recent_sessions(self, *, limit=None):
        return [{"session_key": "desktop:local::a", "limit": limit}]

    def lookup_sessions(self, *, query, limit=None, channel=None):
        return [{"query": query, "limit": limit, "channel": channel}]

    def get_default_session(self, *, channel=None, scope=None, session_key=None):
        return {"channel": channel, "scope": scope, "session_key": session_key}

    def resolve_session_ref(self, *, session_ref):
        return {
            "session_ref": session_ref,
            "session_key": "desktop:local::target",
            "channel": "desktop",
            "availability": "active",
            "identity_ref": "ident:test",
            "binding_key": "channel=desktop|peer=local",
        }

    def get_session(self, *, key):
        title = "Current Session" if key == "desktop:local::current" else "Target Session"
        return {
            "key": key,
            "updated_at": "2026-03-19T10:00:00Z",
            "message_count": 3,
            "has_messages": True,
            "view": {"title": title},
        }

    def read_transcript(self, *, key, request):
        if request.transcript_ref == "bad-ref":
            raise ValueError("transcript_ref_mismatch")
        return TranscriptPage(
            session_key=key,
            mode=request.mode,
            transcript_ref="ref-1",
            total_messages=3,
            start_offset=1,
            end_offset=3,
            messages=[{"role": "assistant", "content": "hello", "timestamp": "ignored"}],
            previous_cursor="prev-1",
            next_cursor="",
            has_more_before=True,
            has_more_after=False,
        )

    def resolve_delivery_target(self, *, session_ref):
        return {
            "session_ref": session_ref,
            "session_key": "desktop:local::target",
            "channel": "telegram",
            "chat_id": "6374137703",
            "metadata": {"message_thread_id": 42},
        }


class ControlPublisherDouble:
    def __init__(self) -> None:
        self.published: list[ControlEvent] = []

    async def publish(self, event: ControlEvent) -> None:
        self.published.append(event)


def set_session_directory_context(tool) -> None:
    tool.set_context(
        SessionDirectoryToolContext(
            channel="desktop",
            chat_id="local",
            session_key="desktop:local::current",
            lang="zh",
            message_id="42",
        )
    )


def build_session(manager: SessionManager, key: str, messages: list[tuple[str, str]]) -> None:
    session = manager.get_or_create(key)
    for role, content in messages:
        session.add_message(role, content)
    manager.save(session)


def run_tool_json(tool, **kwargs):
    return json.loads(asyncio.run(tool.execute(**kwargs)))
