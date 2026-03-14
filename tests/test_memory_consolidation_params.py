from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bao.agent.loop import AgentLoop
from bao.bus.queue import MessageBus


@pytest.mark.asyncio
async def test_memory_consolidation_inherits_generation_parameters(tmp_path) -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(
        return_value=SimpleNamespace(
            content='{"history_entry":"[2026-03-12 12:00] summary","memory_updates":{}}'
        )
    )
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
        temperature=0.25,
        max_tokens=321,
        reasoning_effort="low",
        service_tier="priority",
    )
    loop.context.memory.read_long_term = MagicMock(return_value="")
    loop.context.memory.append_history = MagicMock()
    loop.context.memory.write_categorized_memory = MagicMock()

    session = SimpleNamespace(
        key="telegram:1",
        last_consolidated=0,
        messages=[
            {"role": "user", "content": "hello", "timestamp": "2026-03-12 12:00:00"},
            {"role": "assistant", "content": "world", "timestamp": "2026-03-12 12:00:10"},
        ],
    )

    await loop._consolidate_memory(session, archive_all=True)

    kwargs = provider.chat.await_args.kwargs
    assert kwargs["temperature"] == 0.25
    assert kwargs["max_tokens"] == 321
    assert kwargs["reasoning_effort"] == "low"
    assert kwargs["service_tier"] == "priority"
