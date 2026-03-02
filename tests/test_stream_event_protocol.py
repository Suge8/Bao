"""Tests for StreamEvent v1 protocol."""

import importlib
import time
from unittest.mock import AsyncMock, MagicMock

from bao.agent.loop import AgentLoop, _ToolObservabilityCounters
from bao.agent.protocol import StreamEvent, StreamEventType
from bao.bus.queue import MessageBus
from bao.providers.base import LLMResponse
from bao.providers.retry import PROGRESS_RESET

pytest = importlib.import_module("pytest")


def test_stream_event_defaults():
    ev = StreamEvent(type=StreamEventType.DELTA, text="hello")
    assert ev.type == "delta"
    assert ev.text == "hello"
    assert ev.meta == {}
    assert isinstance(ev.ts, float)
    assert ev.ts > 0


def test_stream_event_frozen():
    ev = StreamEvent(type=StreamEventType.RESET)
    with pytest.raises((AttributeError, TypeError)):
        setattr(ev, "type", "other")


def test_stream_event_meta():
    ev = StreamEvent(type=StreamEventType.TOOL_START, meta={"tool_name": "exec"})
    assert ev.meta["tool_name"] == "exec"
    assert ev.text is None


def test_all_event_types_are_strings():
    for attr in (
        "DELTA",
        "RESET",
        "TOOL_HINT",
        "TOOL_START",
        "TOOL_END",
        "TASK_STATUS",
        "ERROR",
        "FINAL",
    ):
        val = getattr(StreamEventType, attr)
        assert isinstance(val, str)
        assert len(val) > 0


async def test_on_event_callback_receives_delta_and_reset():
    """Simulate the loop calling on_event with delta then reset."""
    events: list[StreamEvent] = []

    async def on_event(ev: StreamEvent) -> None:
        events.append(ev)

    # Simulate what the loop does: delta chunk then reset
    await on_event(StreamEvent(type=StreamEventType.DELTA, text="chunk1"))
    await on_event(StreamEvent(type=StreamEventType.RESET))
    await on_event(StreamEvent(type=StreamEventType.DELTA, text="chunk2"))

    assert events[0].type == StreamEventType.DELTA
    assert events[0].text == "chunk1"
    assert events[1].type == StreamEventType.RESET
    assert events[1].text is None
    assert events[2].type == StreamEventType.DELTA
    assert events[2].text == "chunk2"


def test_stream_event_ts_monotone():
    ev1 = StreamEvent(type=StreamEventType.DELTA, text="a")
    time.sleep(0.001)
    ev2 = StreamEvent(type=StreamEventType.DELTA, text="b")
    assert ev2.ts >= ev1.ts


@pytest.mark.asyncio
async def test_chat_once_emits_reset_and_delta_with_event_only(tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    async def fake_chat(*, on_progress=None, **kwargs):
        del kwargs
        if on_progress:
            await on_progress("chunk-event-only")
        return LLMResponse(content="ok")

    provider.chat = AsyncMock(side_effect=fake_chat)
    loop = AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path, model="test-model")

    events: list[tuple[str, str | None]] = []

    async def on_event(ev: StreamEvent) -> None:
        events.append((ev.type, ev.text))

    await loop._chat_once_with_selected_tools(
        messages=[{"role": "user", "content": "hello"}],
        initial_messages=[{"role": "user", "content": "hello"}],
        iteration=2,
        on_progress=None,
        current_task_ref=None,
        tool_signal_text=None,
        force_final_response=True,
        counters=_ToolObservabilityCounters(),
        on_event=on_event,
    )

    assert events[0] == (StreamEventType.RESET, None)
    assert events[1] == (StreamEventType.DELTA, "chunk-event-only")


@pytest.mark.asyncio
async def test_chat_once_keeps_progress_then_event_order(tmp_path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    async def fake_chat(*, on_progress=None, **kwargs):
        del kwargs
        if on_progress:
            await on_progress("chunk-order")
        return LLMResponse(content="ok")

    provider.chat = AsyncMock(side_effect=fake_chat)
    loop = AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path, model="test-model")

    call_order: list[tuple[str, str | None]] = []

    async def on_progress(chunk: str) -> None:
        call_order.append(("progress", chunk))

    async def on_event(ev: StreamEvent) -> None:
        if ev.type == StreamEventType.RESET:
            call_order.append(("event_reset", ev.text))
        elif ev.type == StreamEventType.DELTA:
            call_order.append(("event_delta", ev.text))

    await loop._chat_once_with_selected_tools(
        messages=[{"role": "user", "content": "hello"}],
        initial_messages=[{"role": "user", "content": "hello"}],
        iteration=2,
        on_progress=on_progress,
        current_task_ref=None,
        tool_signal_text=None,
        force_final_response=True,
        counters=_ToolObservabilityCounters(),
        on_event=on_event,
    )

    assert call_order == [
        ("progress", PROGRESS_RESET),
        ("event_reset", None),
        ("progress", "chunk-order"),
        ("event_delta", "chunk-order"),
    ]
