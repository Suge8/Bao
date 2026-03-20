"""Subagent control-event helper and integration tests."""

import pathlib
import tempfile
from unittest.mock import AsyncMock, MagicMock, call

from bao.agent._subagent_status_runtime import ChildResultRequest
from bao.agent._subagent_types import AnnounceResultRequest
from bao.bus.queue import MessageBus
from bao.session.manager import SessionManager
from tests._subagent_progress_testkit import pytest

pytest_plugins = ("tests._subagent_progress_testkit",)
pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.mark.asyncio
async def test_announce_result_publishes_structured_control_event(manager):
    manager.bus.publish_control = AsyncMock()

    await manager._announce_result(
        AnnounceResultRequest(
            task_id="task123",
            label="research",
            task="look into memory flow",
            result="Found the duplication path.",
            origin={"channel": "desktop", "chat_id": "local", "session_key": "desktop:local"},
            status="ok",
        )
    )

    manager.bus.publish_control.assert_awaited_once()
    await_args = manager.bus.publish_control.await_args
    assert await_args is not None
    event = await_args.args[0]
    assert event.kind == "subagent_result"
    assert event.source == "subagent"
    assert event.origin_channel == "desktop"
    assert event.origin_chat_id == "local"
    assert event.session_key == "desktop:local"
    assert event.payload == {
        "type": "subagent_result",
        "task_id": "task123",
        "label": "research",
        "task": "look into memory flow",
        "status": "ok",
        "result": "Found the duplication path.",
    }


def test_shared_subagent_result_event_helpers_normalize_contract():
    from bao.agent import shared

    event = shared.build_subagent_result_event(
        shared.SubagentResultEventRequest(
            task_id=" task123 ",
            label=" research ",
            task=" look into memory flow ",
            status="unexpected",
            result=" done ",
        )
    )

    assert event == {
        "type": "subagent_result",
        "task_id": "task123",
        "label": "research",
        "task": "look into memory flow",
        "status": "ok",
        "result": "done",
    }
    parsed = shared.parse_subagent_result_payload(event)
    assert parsed == event


def test_persist_child_result_clears_runtime_overlay_but_keeps_stable_status(manager, tmp_path):
    session_manager = SessionManager(tmp_path)
    manager.sessions = session_manager
    child_key = "desktop:local::child"

    manager._persist_child_user_turn(
        child_key,
        parent_session_key="desktop:local",
        label="research",
        task_id="task-1",
        task="inspect runtime",
    )

    session_before = session_manager.get_or_create(child_key)
    assert session_before.metadata.get("child_status") == "running"
    assert session_before.metadata.get("active_task_id") == "task-1"

    manager._persist_child_result(
        ChildResultRequest(
            child_session_key=child_key,
            parent_session_key="desktop:local",
            label="research",
            task_id="task-1",
            result="done",
            status="completed",
        )
    )

    session_after = session_manager.get_or_create(child_key)
    assert session_after.metadata.get("child_status") == "completed"
    assert session_after.metadata.get("active_task_id") in ("", None)


@pytest.mark.asyncio
async def test_handle_stop_cancels_natural_and_active_session_subagents():
    from bao.agent.loop import AgentLoop
    from bao.bus.events import InboundMessage

    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with tempfile.TemporaryDirectory() as td:
        loop = AgentLoop(
            bus=loop_bus,
            provider=provider,
            workspace=pathlib.Path(td),
            model="test-model",
        )

        natural_key = "telegram:1"
        active_key = "telegram:1::s2"
        loop.sessions.set_active_session_key(natural_key, active_key)

        loop.subagents.cancel_by_session = AsyncMock(return_value=0)

        await loop._handle_stop(
            InboundMessage(
                channel="telegram",
                sender_id="user",
                chat_id="1",
                content="/stop",
            )
        )

        assert loop.subagents.cancel_by_session.await_args_list == [
            call(natural_key, wait=False),
            call(active_key, wait=False),
        ]
