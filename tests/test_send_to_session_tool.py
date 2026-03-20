from __future__ import annotations

import asyncio

from bao.agent._session_handoff import SESSION_HANDOFF_REQUEST_EVENT_TYPE
from bao.agent.tool_result import ToolExecutionResult, tool_result_excerpt
from bao.agent.tools.session_directory import SendToSessionTool
from bao.bus.events import ControlEvent
from tests._session_directory_testkit import (
    ControlPublisherDouble,
    FakeDirectory,
    set_session_directory_context,
)


def test_send_to_session_rejects_current_session() -> None:
    publisher = ControlPublisherDouble()
    tool = SendToSessionTool(FakeDirectory(), publisher.publish)
    set_session_directory_context(tool)

    result = asyncio.run(tool.execute(session_key="desktop:local::current", content="hello"))

    assert isinstance(result, ToolExecutionResult)
    assert result.code == "invalid_params"
    assert "cannot target the current session" in tool_result_excerpt(result)
    assert "Do not claim success" in tool_result_excerpt(result)


def test_send_to_session_returns_delivery_error_when_publish_fails() -> None:
    class FailingPublisher:
        async def publish(self, _event: ControlEvent) -> None:
            raise RuntimeError("session send failed")

    tool = SendToSessionTool(FakeDirectory(), FailingPublisher().publish)
    set_session_directory_context(tool)

    result = asyncio.run(tool.execute(session_ref="sess_target", content="hello there"))

    assert isinstance(result, ToolExecutionResult)
    assert result.code == "delivery_failed"
    assert "Error sending to session: session send failed" in tool_result_excerpt(result)
    assert "Do not claim success" in tool_result_excerpt(result)


def test_send_to_session_rejects_target_without_deliverable_route() -> None:
    class NoRouteDirectory(FakeDirectory):
        def resolve_delivery_target(self, *, session_ref):
            return {}

    publisher = ControlPublisherDouble()
    tool = SendToSessionTool(NoRouteDirectory(), publisher.publish)
    set_session_directory_context(tool)

    result = asyncio.run(tool.execute(session_ref="sess_target", content="hello there"))

    assert isinstance(result, ToolExecutionResult)
    assert result.code == "delivery_failed"
    assert "does not have a deliverable external route yet" in tool_result_excerpt(result)
    assert not publisher.published


def test_send_to_session_resolves_session_ref_and_publishes_handoff_request() -> None:
    publisher = ControlPublisherDouble()
    tool = SendToSessionTool(FakeDirectory(), publisher.publish)
    set_session_directory_context(tool)

    result = asyncio.run(tool.execute(session_ref="sess_target", content="hello there"))

    assert result == "Session handoff queued for Telegram session (Target Session): hello there"
    assert len(publisher.published) == 1
    event = publisher.published[0]
    assert event.kind == SESSION_HANDOFF_REQUEST_EVENT_TYPE
    assert event.session_key == "desktop:local::target"
    assert event.origin_channel == "desktop"
    assert event.origin_chat_id == "local"
    assert event.payload["source_session_key"] == "desktop:local::current"
    assert event.payload["source_metadata"] == {"message_id": "42"}
    assert event.payload["source_label"] == "Current Session"
    assert event.payload["target_session_key"] == "desktop:local::target"
    assert event.payload["target_session_ref"] == "sess_target"
    assert event.payload["target_channel"] == "telegram"
    assert event.payload["target_chat_id"] == "6374137703"
    assert event.payload["target_label"] == "Target Session"
    assert event.payload["content"] == "hello there"
