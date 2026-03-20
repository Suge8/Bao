from __future__ import annotations

import importlib
from unittest.mock import MagicMock

from bao.agent import plan
from bao.bus.events import InboundMessage
from bao.bus.queue import MessageBus
from tests._soft_interrupt_testkit import install_empty_memory, loop_context, workspace_dir

pytest = importlib.import_module("pytest")
pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.mark.asyncio
async def test_interrupt_marks_plan_step_interrupted() -> None:
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with loop_context(loop_bus, provider) as loop:
        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return None, [], [], 0, [], False, True, []

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)
        install_empty_memory(loop)

        session = loop.sessions.get_or_create("telegram:1")
        session.metadata[plan.PLAN_STATE_KEY] = plan.new_plan("goal", ["step1", "step2"])
        loop.sessions.save(session)

        assert await loop._process_message(InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="run")) is None

        updated = loop.sessions.get_or_create("telegram:1")
        state = updated.metadata.get(plan.PLAN_STATE_KEY)
        assert isinstance(state, dict)
        assert "[interrupted]" in state["steps"][0]
        assert state["current_step"] == 2

        loop.sessions.invalidate("telegram:1")
        reloaded = loop.sessions.get_or_create("telegram:1")
        reloaded_state = reloaded.metadata.get(plan.PLAN_STATE_KEY)
        assert isinstance(reloaded_state, dict)
        assert "[interrupted]" in reloaded_state["steps"][0]


@pytest.mark.asyncio
async def test_interrupt_uses_parsed_pending_step_not_string_contains() -> None:
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with loop_context(loop_bus, provider) as loop:
        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return None, [], [], 0, [], False, True, []

        setattr(loop, "_run_agent_loop", fake_run_agent_loop)
        install_empty_memory(loop)

        session = loop.sessions.get_or_create("telegram:1")
        state = plan.new_plan("goal", ["[done] has [pending] literal", "real pending step"])
        state["current_step"] = 1
        session.metadata[plan.PLAN_STATE_KEY] = state
        loop.sessions.save(session)

        assert await loop._process_message(InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="run")) is None

        new_state = loop.sessions.get_or_create("telegram:1").metadata.get(plan.PLAN_STATE_KEY)
        assert isinstance(new_state, dict)
        assert "[done]" in new_state["steps"][0]
        assert "[interrupted]" in new_state["steps"][1]


@pytest.mark.asyncio
async def test_interrupt_with_string_current_step_still_marks_pending() -> None:
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with workspace_dir() as ws:
        from bao.agent.loop import AgentLoop

        loop = AgentLoop(bus=loop_bus, provider=provider, workspace=ws, model="test-model")
        try:
            async def fake_run_agent_loop(initial_messages, **kwargs):
                del initial_messages, kwargs
                return None, [], [], 0, [], False, True, []

            setattr(loop, "_run_agent_loop", fake_run_agent_loop)
            install_empty_memory(loop)

            session = loop.sessions.get_or_create("telegram:1")
            state = plan.new_plan("goal", ["pending one", "pending two"])
            state["current_step"] = "1"
            session.metadata[plan.PLAN_STATE_KEY] = state
            loop.sessions.save(session)

            assert await loop._process_message(InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="run")) is None

            new_state = loop.sessions.get_or_create("telegram:1").metadata.get(plan.PLAN_STATE_KEY)
            assert isinstance(new_state, dict)
            assert "[interrupted]" in new_state["steps"][0]
        finally:
            loop.close()
