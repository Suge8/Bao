from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bao.agent._loop_constants import SESSION_LANG_KEY
from bao.agent._session_handoff import (
    SESSION_HANDOFF_REQUEST_EVENT_TYPE,
    SESSION_HANDOFF_RESULT_EVENT_TYPE,
    SessionHandoffRequest,
    SessionHandoffResult,
)
from bao.agent.loop import AgentLoop
from bao.bus.events import ControlEvent, OutboundMessage
from bao.bus.queue import MessageBus

pytestmark = pytest.mark.integration


def _make_loop(tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    return AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
    )


@pytest.mark.asyncio
async def test_session_handoff_request_event_emits_target_hint_and_queues_result(tmp_path) -> None:
    loop = _make_loop(tmp_path)
    delivered: list[OutboundMessage] = []
    loop.set_delivery_sender(AsyncMock(side_effect=lambda msg: delivered.append(msg)))
    loop.process_direct = AsyncMock(return_value="target done")
    source_session = loop.sessions.get_or_create("imessage:source::main")
    source_session.metadata[SESSION_LANG_KEY] = "zh"
    loop.sessions.save(source_session)
    target_session = loop.sessions.get_or_create("telegram:target::main")
    target_session.metadata[SESSION_LANG_KEY] = "zh"
    loop.sessions.save(target_session)

    request = SessionHandoffRequest(
        handoff_id="h1",
        source_session_key="imessage:source::main",
        source_channel="imessage",
        source_chat_id="+8618127419003",
        target_session_key="telegram:target::main",
        target_channel="telegram",
        target_chat_id="6374137703",
        content="帮我汇报一下任务进展",
    )

    result = await loop._process_control_event(
        ControlEvent(
            kind=SESSION_HANDOFF_REQUEST_EVENT_TYPE,
            payload=request.as_payload(),
            session_key=request.target_session_key,
            origin_channel=request.source_channel,
            origin_chat_id=request.source_chat_id,
            source="send_to_session",
        )
    )

    assert result is None
    assert [item.channel for item in delivered] == ["imessage", "telegram"]
    assert delivered[0].chat_id == "+8618127419003"
    assert delivered[0].content == "📨 已转交到 Telegram 会话：\n帮我汇报一下任务进展"
    assert delivered[1].chat_id == "6374137703"
    assert delivered[1].content == "📨 收到来自 iMessage 会话的请求：\n帮我汇报一下任务进展"

    persisted_source = loop.sessions.get_or_create("imessage:source::main")
    persisted_target = loop.sessions.get_or_create("telegram:target::main")
    assert persisted_source.messages[-1]["content"] == "📨 已转交到 Telegram 会话：\n帮我汇报一下任务进展"
    assert persisted_target.messages[-1]["content"] == "📨 收到来自 iMessage 会话的请求：\n帮我汇报一下任务进展"

    queued = await loop.bus.consume_control()
    assert queued.kind == SESSION_HANDOFF_RESULT_EVENT_TYPE
    assert queued.payload["status"] == "ok"
    assert queued.payload["result"] == "target done"
    loop.process_direct.assert_awaited_once()


@pytest.mark.asyncio
async def test_session_handoff_result_event_emits_source_hint_and_returns_background_outbound(
    tmp_path,
) -> None:
    loop = _make_loop(tmp_path)
    delivered: list[OutboundMessage] = []
    loop.set_delivery_sender(AsyncMock(side_effect=lambda msg: delivered.append(msg)))
    source_session = loop.sessions.get_or_create("imessage:source::main")
    source_session.metadata[SESSION_LANG_KEY] = "zh"
    loop.sessions.save(source_session)
    loop._execute_background_turn = AsyncMock(
        return_value=OutboundMessage(
            channel="imessage",
            chat_id="+8618127419003",
            content="我已经把 TG 那边的结果整理好了。",
            metadata={"session_key": "imessage:source::main"},
        )
    )
    result_payload = SessionHandoffResult(
        handoff_id="h1",
        source_session_key="imessage:source::main",
        source_channel="imessage",
        source_chat_id="+8618127419003",
        source_metadata={"message_id": "123"},
        target_session_key="telegram:target::main",
        target_channel="telegram",
        request_content="帮我汇报一下任务进展",
        status="ok",
        result="任务已完成",
    )

    outbound = await loop._process_control_event(
        ControlEvent(
            kind=SESSION_HANDOFF_RESULT_EVENT_TYPE,
            payload=result_payload.as_payload(),
            session_key=result_payload.source_session_key,
            origin_channel=result_payload.source_channel,
            origin_chat_id=result_payload.source_chat_id,
            source="session_handoff",
        )
    )

    assert outbound is not None
    assert outbound.content == "我已经把 TG 那边的结果整理好了。"
    assert delivered
    assert delivered[0].channel == "imessage"
    assert delivered[0].chat_id == "+8618127419003"
    assert delivered[0].content == "📨 收到来自 Telegram 会话的回复：\n任务已完成"
    assert delivered[0].metadata["message_id"] == "123"
    persisted = loop.sessions.get_or_create("imessage:source::main")
    assert persisted.messages[-1]["content"] == "📨 收到来自 Telegram 会话的回复：\n任务已完成"
    loop._execute_background_turn.assert_awaited_once()
    turn_input = loop._execute_background_turn.await_args.args[0]
    assert "Original forwarded request" in turn_input.system_prompt_text
    assert "任务已完成" in turn_input.system_prompt_text
