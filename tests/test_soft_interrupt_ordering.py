from __future__ import annotations

import importlib
from unittest.mock import MagicMock

from bao.bus.events import InboundMessage
from bao.bus.queue import MessageBus
from tests._soft_interrupt_testkit import install_empty_memory, loop_context

pytest = importlib.import_module("pytest")
pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.mark.asyncio
async def test_interrupt_preserves_tool_order_with_presaved_current_message():
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with loop_context(loop_bus, provider) as loop:
        completed_tool_msgs = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "name": "read_file", "content": "ok"},
        ]

        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return None, [], [], 0, [], False, True, completed_tool_msgs

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)
        install_empty_memory(loop)

        dispatch_key = "telegram:1"
        current_token = "tok-current"
        newer_token = "tok-newer"
        session = loop.sessions.get_or_create(dispatch_key)
        session.add_message("user", "m2", _pre_saved=True, _pre_saved_token=current_token)
        session.add_message("user", "m3", _pre_saved=True, _pre_saved_token=newer_token)
        loop.sessions.save(session)

        msg = InboundMessage(
            channel="telegram",
            sender_id="u",
            chat_id="1",
            content="m2",
            metadata={"_pre_saved": True, "_pre_saved_token": current_token},
        )
        assert await loop._process_message(msg) is None

        updated = loop.sessions.get_or_create(dispatch_key)
        idx_current = next(i for i, m in enumerate(updated.messages) if m.get("_pre_saved_token") == current_token)
        idx_newer = next(i for i, m in enumerate(updated.messages) if m.get("_pre_saved_token") == newer_token)
        idx_assistant = next(i for i, m in enumerate(updated.messages) if m.get("role") == "assistant" and m.get("tool_calls"))
        idx_tool = next(i for i, m in enumerate(updated.messages) if m.get("tool_call_id") == "call_1")
        assert idx_current < idx_assistant < idx_tool < idx_newer


@pytest.mark.asyncio
async def test_presaved_fallback_removes_only_presaved_history_item() -> None:
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with loop_context(loop_bus, provider) as loop:
        captured: dict[str, list[dict[str, object]]] = {}

        async def fake_run_agent_loop(initial_messages, **kwargs):
            del kwargs
            captured["messages"] = initial_messages
            return "ok", [], [], 0, [], False, False, []

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)
        install_empty_memory(loop)

        session = loop.sessions.get_or_create("telegram:1")
        session.add_message("user", "m2", _pre_saved=True, _pre_saved_token="tok-old")
        loop.sessions.save(session)

        msg = InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="m2", metadata={"_pre_saved": True})
        assert await loop._process_message(msg) is not None

        user_count = sum(
            1
            for item in captured["messages"]
            if item.get("role") == "user" and item.get("content") == "m2"
        )
        assert user_count == 1


@pytest.mark.asyncio
async def test_interrupt_non_presaved_fallback_skips_newer_presaved_same_content() -> None:
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with loop_context(loop_bus, provider) as loop:
        completed_tool_msgs = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_same_content", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "call_same_content", "name": "read_file", "content": "ok"},
        ]

        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return None, [], [], 0, [], False, True, completed_tool_msgs

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)
        install_empty_memory(loop)

        dispatch_key = "telegram:1"
        session = loop.sessions.get_or_create(dispatch_key)
        session.add_message("user", "ok")
        session.add_message("user", "ok", _pre_saved=True, _pre_saved_token="tok-new")
        loop.sessions.save(session)

        msg = InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="ok", metadata={"_ephemeral": True})
        assert await loop._process_message(msg) is None

        updated = loop.sessions.get_or_create(dispatch_key)
        idx_regular = next(i for i, m in enumerate(updated.messages) if m.get("role") == "user" and not m.get("_pre_saved"))
        idx_presaved = next(i for i, m in enumerate(updated.messages) if m.get("_pre_saved_token") == "tok-new")
        idx_assistant = next(i for i, m in enumerate(updated.messages) if m.get("role") == "assistant" and m.get("tool_calls"))
        idx_tool = next(i for i, m in enumerate(updated.messages) if m.get("tool_call_id") == "call_same_content")
        assert idx_regular < idx_assistant < idx_tool < idx_presaved


@pytest.mark.asyncio
async def test_interrupt_insert_fallback_appends_when_target_user_missing() -> None:
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with loop_context(loop_bus, provider) as loop:
        completed_tool_msgs = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_missing", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "call_missing", "name": "read_file", "content": "ok"},
        ]

        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return None, [], [], 0, [], False, True, completed_tool_msgs

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)
        install_empty_memory(loop)

        session = loop.sessions.get_or_create("telegram:1")
        session.add_message("user", "existing-user")
        session.add_message("assistant", "existing-assistant")
        loop.sessions.save(session)

        msg = InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="missing-user-turn", metadata={"_ephemeral": True})
        assert await loop._process_message(msg) is None

        updated = loop.sessions.get_or_create("telegram:1")
        assert updated.messages[-2].get("role") == "assistant"
        assert updated.messages[-1].get("tool_call_id") == "call_missing"


@pytest.mark.asyncio
async def test_model_error_response_persisted_as_error_and_returned() -> None:
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with loop_context(loop_bus, provider) as loop:
        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return "boom", [], [], 0, [], True, False, []

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)
        install_empty_memory(loop)

        session = loop.sessions.get_or_create("telegram:1")
        session.metadata["title"] = "fixed"
        loop.sessions.save(session)

        out = await loop._process_message(
            InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="trigger")
        )
        assert out is not None
        assert out.content == "boom"

        updated = loop.sessions.get_or_create("telegram:1")
        assistant_msgs = [m for m in updated.messages if m.get("role") == "assistant"]
        assert any(m.get("role") == "user" and m.get("content") == "trigger" for m in updated.messages)
        assert assistant_msgs[-1].get("content") == "boom"
        assert assistant_msgs[-1].get("status") == "error"
