from __future__ import annotations

import asyncio
import importlib
from unittest.mock import MagicMock

from bao.bus.events import InboundMessage
from bao.bus.queue import MessageBus
from tests._soft_interrupt_testkit import install_empty_memory, loop_context

pytest = importlib.import_module("pytest")
pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.mark.asyncio
async def test_agent_stop_unblocks_idle_run():
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with loop_context(loop_bus, provider) as loop:
        async def noop_mcp():
            pass

        loop._connect_mcp = noop_mcp
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

    with loop_context(loop_bus, provider) as loop:
        async def noop_mcp():
            pass

        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return "ok", [], [], 0, [], False, False, []

        loop._connect_mcp = noop_mcp
        setattr(loop, "_run_agent_loop", fake_run_agent_loop)
        install_empty_memory(loop)

        dispatch_key = "telegram:1"
        release_busy = asyncio.Event()
        busy_started = asyncio.Event()

        async def busy_job() -> None:
            async with loop._session_runs.run_scope(dispatch_key):
                busy_started.set()
                await release_busy.wait()

        busy = loop._session_runs.schedule(dispatch_key, busy_job())
        await busy_started.wait()

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
            assert loop._session_runs.generation(dispatch_key) >= 1
        finally:
            loop._running = False
            release_busy.set()
            busy.cancel()
            runner.cancel()
            await asyncio.gather(busy, runner, return_exceptions=True)
