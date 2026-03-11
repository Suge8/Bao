import asyncio
import gc
import importlib
import pathlib
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from bao.agent import plan
from bao.bus.events import InboundMessage
from bao.bus.queue import MessageBus
from bao.utils.db import close_db

if TYPE_CHECKING:
    from bao.agent.loop import AgentLoop

pytest = importlib.import_module("pytest")
pytestmark = [pytest.mark.integration, pytest.mark.slow]


@contextmanager
def _workspace_dir() -> Iterator[pathlib.Path]:
    with tempfile.TemporaryDirectory() as td:
        ws = pathlib.Path(td)
        (ws / "PERSONA.md").write_text("# Persona\n", encoding="utf-8")
        (ws / "INSTRUCTIONS.md").write_text("# Instructions\n", encoding="utf-8")
        try:
            yield ws
        finally:
            close_db(ws)


@contextmanager
def _test_loop(loop_bus: MessageBus, provider: MagicMock) -> Iterator["AgentLoop"]:
    with _workspace_dir() as ws:
        from bao.agent.loop import AgentLoop

        loop = AgentLoop(
            bus=loop_bus,
            provider=provider,
            workspace=ws,
            model="test-model",
        )
        try:
            yield loop
        finally:
            loop.close()
            del loop
            gc.collect()


@pytest.mark.asyncio
async def test_agent_stop_unblocks_idle_run():
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with _test_loop(loop_bus, provider) as loop:

        async def _noop_mcp():
            pass

        loop._connect_mcp = _noop_mcp

        runner = asyncio.create_task(loop.run())
        try:
            await asyncio.sleep(0)
            loop.stop()
            await asyncio.wait_for(runner, timeout=0.5)
        finally:
            if not runner.done():
                runner.cancel()
                await asyncio.gather(runner, return_exceptions=True)


@pytest.mark.asyncio
async def test_soft_interrupt_presaves_user_message_when_busy():
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with _test_loop(loop_bus, provider) as loop:

        async def _noop_mcp():
            pass

        loop._connect_mcp = _noop_mcp

        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return "ok", [], [], 0, [], False, False, []

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)

        def _search_memory(query: str, limit: int = 5) -> list[str]:
            del query, limit
            return []

        def _search_experience(query: str, limit: int = 3) -> list[str]:
            del query, limit
            return []

        loop.context.memory.search_memory = _search_memory
        loop.context.memory.search_experience = _search_experience

        dispatch_key = "telegram:1"
        busy = asyncio.create_task(asyncio.sleep(5))
        loop._active_tasks[dispatch_key] = [busy]

        loop._running = True
        runner = asyncio.create_task(loop.run())
        try:
            await loop_bus.publish_inbound(
                InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="m2")
            )

            await asyncio.sleep(0.1)

            session = loop.sessions.get_or_create(dispatch_key)
            presaved = next(
                (
                    m
                    for m in session.messages
                    if m.get("role") == "user"
                    and m.get("content") == "m2"
                    and m.get("_pre_saved") is True
                ),
                None,
            )
            assert presaved is not None
            token = presaved.get("_pre_saved_token")
            assert isinstance(token, str) and token
            assert loop._session_generations.get(dispatch_key, 0) >= 1
        finally:
            loop._running = False
            busy.cancel()
            runner.cancel()
            await asyncio.gather(busy, runner, return_exceptions=True)


@pytest.mark.asyncio
async def test_interrupt_preserves_tool_order_with_presaved_current_message():
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with _test_loop(loop_bus, provider) as loop:
        completed_tool_msgs = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "name": "read_file",
                "content": "ok",
            },
        ]

        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return None, [], [], 0, [], False, True, completed_tool_msgs

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)

        def _search_memory(query: str, limit: int = 5) -> list[str]:
            del query, limit
            return []

        def _search_experience(query: str, limit: int = 3) -> list[str]:
            del query, limit
            return []

        loop.context.memory.search_memory = _search_memory
        loop.context.memory.search_experience = _search_experience

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

        out = await loop._process_message(msg)
        assert out is None

        updated = loop.sessions.get_or_create(dispatch_key)
        idx_current = next(
            i
            for i, m in enumerate(updated.messages)
            if m.get("role") == "user" and m.get("_pre_saved_token") == current_token
        )
        idx_newer = next(
            i
            for i, m in enumerate(updated.messages)
            if m.get("role") == "user" and m.get("_pre_saved_token") == newer_token
        )
        idx_assistant = next(
            i
            for i, m in enumerate(updated.messages)
            if m.get("role") == "assistant" and m.get("tool_calls")
        )
        idx_tool = next(
            i
            for i, m in enumerate(updated.messages)
            if m.get("role") == "tool" and m.get("tool_call_id") == "call_1"
        )

        assert idx_current < idx_assistant < idx_tool < idx_newer


@pytest.mark.asyncio
async def test_presaved_fallback_removes_only_presaved_history_item() -> None:
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with _test_loop(loop_bus, provider) as loop:
        captured: dict[str, list[dict[str, object]]] = {}

        async def fake_run_agent_loop(initial_messages, **kwargs):
            del kwargs
            captured["messages"] = initial_messages
            return "ok", [], [], 0, [], False, False, []

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)

        def _search_memory(query: str, limit: int = 5) -> list[str]:
            del query, limit
            return []

        def _search_experience(query: str, limit: int = 3) -> list[str]:
            del query, limit
            return []

        loop.context.memory.search_memory = _search_memory
        loop.context.memory.search_experience = _search_experience

        dispatch_key = "telegram:1"
        session = loop.sessions.get_or_create(dispatch_key)
        session.add_message("user", "m2", _pre_saved=True, _pre_saved_token="tok-old")
        loop.sessions.save(session)

        msg = InboundMessage(
            channel="telegram",
            sender_id="u",
            chat_id="1",
            content="m2",
            metadata={"_pre_saved": True},
        )

        out = await loop._process_message(msg)
        assert out is not None

        initial_messages = captured["messages"]
        user_count = sum(
            1
            for item in initial_messages
            if item.get("role") == "user" and item.get("content") == "m2"
        )
        assert user_count == 1


@pytest.mark.asyncio
async def test_interrupt_non_presaved_fallback_skips_newer_presaved_same_content() -> None:
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with _test_loop(loop_bus, provider) as loop:
        completed_tool_msgs = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_same_content",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_same_content",
                "name": "read_file",
                "content": "ok",
            },
        ]

        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return None, [], [], 0, [], False, True, completed_tool_msgs

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)

        def _search_memory(query: str, limit: int = 5) -> list[str]:
            del query, limit
            return []

        def _search_experience(query: str, limit: int = 3) -> list[str]:
            del query, limit
            return []

        loop.context.memory.search_memory = _search_memory
        loop.context.memory.search_experience = _search_experience

        dispatch_key = "telegram:1"
        session = loop.sessions.get_or_create(dispatch_key)
        session.add_message("user", "ok")
        session.add_message("user", "ok", _pre_saved=True, _pre_saved_token="tok-new")
        loop.sessions.save(session)

        msg = InboundMessage(
            channel="telegram",
            sender_id="u",
            chat_id="1",
            content="ok",
            metadata={"_ephemeral": True},
        )

        out = await loop._process_message(msg)
        assert out is None

        updated = loop.sessions.get_or_create(dispatch_key)
        idx_regular_user = next(
            i
            for i, m in enumerate(updated.messages)
            if m.get("role") == "user" and m.get("content") == "ok" and not m.get("_pre_saved")
        )
        idx_presaved_user = next(
            i
            for i, m in enumerate(updated.messages)
            if m.get("role") == "user" and m.get("_pre_saved_token") == "tok-new"
        )
        idx_assistant = next(
            i
            for i, m in enumerate(updated.messages)
            if m.get("role") == "assistant" and m.get("tool_calls")
        )
        idx_tool = next(
            i
            for i, m in enumerate(updated.messages)
            if m.get("role") == "tool" and m.get("tool_call_id") == "call_same_content"
        )

        assert idx_regular_user < idx_assistant < idx_tool < idx_presaved_user


@pytest.mark.asyncio
async def test_interrupt_insert_fallback_appends_when_target_user_missing() -> None:
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with _test_loop(loop_bus, provider) as loop:
        completed_tool_msgs = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_missing",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_missing",
                "name": "read_file",
                "content": "ok",
            },
        ]

        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return None, [], [], 0, [], False, True, completed_tool_msgs

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)

        def _search_memory(query: str, limit: int = 5) -> list[str]:
            del query, limit
            return []

        def _search_experience(query: str, limit: int = 3) -> list[str]:
            del query, limit
            return []

        loop.context.memory.search_memory = _search_memory
        loop.context.memory.search_experience = _search_experience

        dispatch_key = "telegram:1"
        session = loop.sessions.get_or_create(dispatch_key)
        session.add_message("user", "existing-user")
        session.add_message("assistant", "existing-assistant")
        loop.sessions.save(session)

        msg = InboundMessage(
            channel="telegram",
            sender_id="u",
            chat_id="1",
            content="missing-user-turn",
            metadata={"_ephemeral": True},
        )

        out = await loop._process_message(msg)
        assert out is None

        updated = loop.sessions.get_or_create(dispatch_key)
        assert updated.messages[-2].get("role") == "assistant"
        assert updated.messages[-1].get("role") == "tool"
        assert updated.messages[-1].get("tool_call_id") == "call_missing"


@pytest.mark.asyncio
async def test_model_error_response_persisted_as_error_and_returned() -> None:
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with _test_loop(loop_bus, provider) as loop:

        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return "boom", [], [], 0, [], True, False, []

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)

        def _search_memory(query: str, limit: int = 5) -> list[str]:
            del query, limit
            return []

        def _search_experience(query: str, limit: int = 3) -> list[str]:
            del query, limit
            return []

        loop.context.memory.search_memory = _search_memory
        loop.context.memory.search_experience = _search_experience

        dispatch_key = "telegram:1"
        session = loop.sessions.get_or_create(dispatch_key)
        session.metadata["title"] = "fixed"
        loop.sessions.save(session)

        out = await loop._process_message(
            InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="trigger")
        )

        assert out is not None
        assert out.content == "boom"

        updated = loop.sessions.get_or_create(dispatch_key)
        assert any(
            m.get("role") == "user" and m.get("content") == "trigger" for m in updated.messages
        )
        assistant_msgs = [m for m in updated.messages if m.get("role") == "assistant"]
        assert assistant_msgs
        assert assistant_msgs[-1].get("content") == "boom"
        assert assistant_msgs[-1].get("status") == "error"


@pytest.mark.asyncio
async def test_interrupt_marks_plan_step_interrupted() -> None:
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with _test_loop(loop_bus, provider) as loop:

        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return None, [], [], 0, [], False, True, []

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)

        def _search_memory(query: str, limit: int = 5) -> list[str]:
            del query, limit
            return []

        def _search_experience(query: str, limit: int = 3) -> list[str]:
            del query, limit
            return []

        loop.context.memory.search_memory = _search_memory
        loop.context.memory.search_experience = _search_experience

        dispatch_key = "telegram:1"
        session = loop.sessions.get_or_create(dispatch_key)
        session.metadata[plan.PLAN_STATE_KEY] = plan.new_plan("goal", ["step1", "step2"])
        loop.sessions.save(session)

        msg = InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="run")
        out = await loop._process_message(msg)
        assert out is None

        updated = loop.sessions.get_or_create(dispatch_key)
        state = updated.metadata.get(plan.PLAN_STATE_KEY)
        assert isinstance(state, dict)
        assert "[interrupted]" in state["steps"][0]
        assert state["current_step"] == 2

        loop.sessions.invalidate(dispatch_key)
        reloaded = loop.sessions.get_or_create(dispatch_key)
        reloaded_state = reloaded.metadata.get(plan.PLAN_STATE_KEY)
        assert isinstance(reloaded_state, dict)
        assert "[interrupted]" in reloaded_state["steps"][0]


@pytest.mark.asyncio
async def test_interrupt_uses_parsed_pending_step_not_string_contains() -> None:
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with _test_loop(loop_bus, provider) as loop:

        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return None, [], [], 0, [], False, True, []

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)

        def _search_memory(query: str, limit: int = 5) -> list[str]:
            del query, limit
            return []

        def _search_experience(query: str, limit: int = 3) -> list[str]:
            del query, limit
            return []

        loop.context.memory.search_memory = _search_memory
        loop.context.memory.search_experience = _search_experience

        dispatch_key = "telegram:1"
        session = loop.sessions.get_or_create(dispatch_key)
        state = plan.new_plan("goal", ["[done] has [pending] literal", "real pending step"])
        state["current_step"] = 1
        session.metadata[plan.PLAN_STATE_KEY] = state
        loop.sessions.save(session)

        msg = InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="run")
        out = await loop._process_message(msg)
        assert out is None

        updated = loop.sessions.get_or_create(dispatch_key)
        new_state = updated.metadata.get(plan.PLAN_STATE_KEY)
        assert isinstance(new_state, dict)
        assert "[done]" in new_state["steps"][0]
        assert "[interrupted]" in new_state["steps"][1]


@pytest.mark.asyncio
async def test_interrupt_with_string_current_step_still_marks_pending() -> None:
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with _workspace_dir() as ws:
        from bao.agent.loop import AgentLoop

        loop = AgentLoop(
            bus=loop_bus,
            provider=provider,
            workspace=ws,
            model="test-model",
        )

        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return None, [], [], 0, [], False, True, []

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)

        loop.context.memory.search_memory = lambda query, limit=5: []
        loop.context.memory.search_experience = lambda query, limit=3: []

        dispatch_key = "telegram:1"
        session = loop.sessions.get_or_create(dispatch_key)
        state = plan.new_plan("goal", ["pending one", "pending two"])
        state["current_step"] = "1"
        session.metadata[plan.PLAN_STATE_KEY] = state
        loop.sessions.save(session)

        msg = InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="run")
        out = await loop._process_message(msg)
        assert out is None

        updated = loop.sessions.get_or_create(dispatch_key)
        new_state = updated.metadata.get(plan.PLAN_STATE_KEY)
        assert isinstance(new_state, dict)
        assert "[interrupted]" in new_state["steps"][0]
