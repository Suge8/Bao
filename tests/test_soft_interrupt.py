import asyncio
import importlib
import pathlib
import tempfile
from unittest.mock import MagicMock

from bao.bus.events import InboundMessage
from bao.bus.queue import MessageBus

pytest = importlib.import_module("pytest")


@pytest.mark.asyncio
async def test_soft_interrupt_presaves_user_message_when_busy():
    loop_bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with tempfile.TemporaryDirectory() as td:
        from bao.agent.loop import AgentLoop

        ws = pathlib.Path(td)
        (ws / "PERSONA.md").write_text("# Persona\n", encoding="utf-8")
        (ws / "INSTRUCTIONS.md").write_text("# Instructions\n", encoding="utf-8")

        loop = AgentLoop(
            bus=loop_bus,
            provider=provider,
            workspace=ws,
            model="test-model",
        )

        async def _noop_mcp():
            pass

        loop._connect_mcp = _noop_mcp

        async def fake_run_agent_loop(initial_messages, **kwargs):
            del initial_messages, kwargs
            return "ok", [], [], 0, [], False

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
            assert any(
                m.get("role") == "user" and m.get("content") == "m2" for m in session.messages
            )
            assert loop._session_generations.get(dispatch_key, 0) >= 1
        finally:
            loop._running = False
            busy.cancel()
            runner.cancel()
            await asyncio.gather(busy, runner, return_exceptions=True)
