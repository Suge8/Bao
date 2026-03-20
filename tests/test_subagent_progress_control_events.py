"""Subagent progress tests around AgentLoop control events and payload contract."""

from unittest.mock import MagicMock

from bao.bus.events import ControlEvent
from bao.bus.queue import MessageBus
from tests._subagent_progress_testkit import process_control_event, pytest

pytest_plugins = ("tests._subagent_progress_testkit",)
pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _reply_attachment_payload(attachment_path) -> list[dict[str, object]]:
    return [
        {
            "fileName": "friendly.png",
            "filePath": str(attachment_path),
            "path": "artifacts/reply.png",
            "mimeType": "image/png",
            "sizeBytes": 3,
            "isImage": True,
            "extensionLabel": "PNG",
        }
    ]


def _assert_persisted_attachment(loop, session_key: str) -> None:
    session = loop.sessions.get_or_create(session_key)
    assert session.messages[-1]["attachments"] == [
        {
            "fileName": "friendly.png",
            "path": "artifacts/reply.png",
            "mimeType": "image/png",
            "size": 3,
            "isImage": True,
            "extensionLabel": "PNG",
        }
    ]


@pytest.mark.asyncio
async def test_on_system_response_fires_for_control_events():
    async def _process(event):
        del event
        from bao.bus.events import OutboundMessage

        return OutboundMessage(
            channel="tg", chat_id="1", content="Subagent finished the research task."
        )

    captured, _ = await process_control_event(
        ControlEvent(
            kind="subagent_result",
            payload={"type": "subagent_result"},
            origin_channel="tg",
            origin_chat_id="1",
            source="subagent",
        ),
        process_override=_process,
    )

    assert len(captured) == 1
    assert captured[0].content == "Subagent finished the research task."


@pytest.mark.asyncio
async def test_control_response_preserves_session_key_metadata():
    async def _run_agent_loop(*args, **kwargs):
        del args, kwargs
        return "done", [], [], 0, []

    def _configure(loop):
        loop.context.memory.search_memory = lambda query, limit=5: []
        loop.context.memory.search_experience = lambda query, limit=3: []

    captured, _ = await process_control_event(
        ControlEvent(
            kind="subagent_result",
            session_key="tg:1::s2",
            origin_channel="tg",
            origin_chat_id="1",
            source="subagent",
            metadata={"origin": "test"},
            payload={
                "type": "subagent_result",
                "task_id": "task-1",
                "label": "research",
                "task": "research topic",
                "status": "ok",
                "result": "done",
            },
        ),
        run_agent_loop=_run_agent_loop,
        configure=_configure,
    )

    assert len(captured) == 1
    assert captured[0].metadata.get("session_key") == "tg:1::s2"
    assert captured[0].metadata.get("origin") == "test"
    assert "control_event" not in captured[0].metadata
    assert "system_event" not in captured[0].metadata


@pytest.mark.asyncio
async def test_process_control_event_uses_structured_path_without_system_message(tmp_path):
    async def _fail_system(*args, **kwargs):
        raise AssertionError("control event should not fallback to _process_system_message")

    async def _run_agent_loop(initial_messages, **kwargs):
        del kwargs
        user_messages = [m for m in initial_messages if m.get("role") == "user"]
        assert user_messages
        assert "[Background task completed successfully]" in user_messages[-1]["content"]
        return "structured ok", [], [], 0, [], False, False, []

    def _configure(loop):
        loop._process_system_message = _fail_system

    captured, loop = await process_control_event(
        ControlEvent(
            kind="subagent_result",
            session_key="desktop:local",
            origin_channel="desktop",
            origin_chat_id="local",
            source="subagent",
            metadata={"origin": "structured"},
            payload={
                "type": "subagent_result",
                "task_id": "task-1",
                "label": "research",
                "task": "inspect runtime flow",
                "status": "ok",
                "result": "done",
            },
        ),
        run_agent_loop=_run_agent_loop,
        configure=_configure,
        workspace=tmp_path,
    )

    assert captured
    result = captured[0]
    assert result.content == "structured ok"
    assert result.metadata["session_key"] == "desktop:local"
    assert result.metadata["origin"] == "structured"


@pytest.mark.asyncio
async def test_process_control_event_persists_reply_attachments_with_single_schema(tmp_path):
    from bao.agent.loop import AgentLoop

    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
    )
    session_key = "desktop:local"
    attachment_path = tmp_path / "artifacts" / "reply.png"
    attachment_path.parent.mkdir()
    attachment_path.write_bytes(b"png")

    async def _fake_run_agent_loop(initial_messages, **kwargs):
        del initial_messages, kwargs
        return ("", [], [], 0, [], False, False, [], _reply_attachment_payload(attachment_path))

    loop._run_agent_loop = _fake_run_agent_loop

    result = await loop._process_control_event(
        ControlEvent(
            kind="subagent_result",
            session_key=session_key,
            origin_channel="desktop",
            origin_chat_id="local",
            source="subagent",
            payload={
                "type": "subagent_result",
                "task_id": "task-1",
                "label": "render",
                "task": "prepare attachment",
                "status": "ok",
                "result": "done",
            },
        )
    )

    assert result is not None
    assert result.content == "\u540e\u53f0\u9644\u4ef6\u5df2\u51c6\u5907\u597d\u3002"
    assert result.media == [str(attachment_path)]
    _assert_persisted_attachment(loop, session_key)
