import asyncio
import importlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from bao.bus.events import InboundMessage
from bao.bus.queue import MessageBus

pytest = importlib.import_module("pytest")


def _make_loop(tmp_path: Path) -> Any:
    from bao.agent.loop import AgentLoop

    (tmp_path / "PERSONA.md").write_text("# Persona\n", encoding="utf-8")
    (tmp_path / "INSTRUCTIONS.md").write_text("# Instructions\n", encoding="utf-8")

    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
    )

    def _search_memory(query: str, limit: int = 5) -> list[str]:
        del query, limit
        return []

    def _search_experience(query: str, limit: int = 3) -> list[str]:
        del query, limit
        return []

    loop.context.memory.search_memory = _search_memory
    loop.context.memory.search_experience = _search_experience
    return loop


@pytest.mark.asyncio
async def test_generate_title_uses_following_assistant_for_first_non_greeting_user(
    tmp_path: Path,
) -> None:
    loop = _make_loop(tmp_path)
    session = loop.sessions.get_or_create("telegram:1")
    session.messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "Build a weekly report template"},
        {"role": "assistant", "content": "Here is a report structure"},
    ]

    captured_prompt: dict[str, str] = {}

    async def _fake_call(system: str, prompt: str) -> dict[str, str]:
        del system
        captured_prompt["value"] = prompt
        return {"title": "Weekly report"}

    loop._call_utility_llm = _fake_call

    await loop._generate_session_title(session)

    prompt = captured_prompt["value"]
    assert "User: Build a weekly report template" in prompt
    assert "Assistant: Here is a report structure" in prompt
    assert "User: hi" not in prompt
    assert session.metadata.get("title") == "Weekly report"


@pytest.mark.asyncio
async def test_generate_title_fallback_uses_text_from_multimodal_user_content(
    tmp_path: Path,
) -> None:
    loop = _make_loop(tmp_path)
    session = loop.sessions.get_or_create("telegram:1")
    session.messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "  Build weekly report  "},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}},
            ],
        },
        {"role": "assistant", "content": "Sure"},
    ]

    async def _fake_call(system: str, prompt: str) -> dict[str, str]:
        del system, prompt
        return {}

    loop._call_utility_llm = _fake_call

    await loop._generate_session_title(session)

    assert session.metadata.get("title") == "Build weekly report"


@pytest.mark.asyncio
async def test_process_message_deduplicates_title_generation_while_inflight(
    tmp_path: Path,
) -> None:
    loop = _make_loop(tmp_path)

    async def _fake_run_agent_loop(initial_messages: list[dict[str, Any]], **kwargs: Any):
        del initial_messages, kwargs
        return "ok", [], [], 0, [], False, []

    loop._run_agent_loop = _fake_run_agent_loop
    loop._maybe_learn_experience = lambda **kwargs: None

    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def _fake_generate_title(_session: Any) -> None:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()

    loop._generate_session_title = _fake_generate_title

    msg1 = InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="first")
    msg2 = InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="second")

    try:
        out1 = await loop._process_message(msg1)
        assert out1 is not None

        await asyncio.wait_for(started.wait(), timeout=1)

        out2 = await loop._process_message(msg2)
        assert out2 is not None
        assert calls == 1
    finally:
        release.set()
        await asyncio.sleep(0)

    assert "telegram:1" not in loop._title_generation_inflight


@pytest.mark.asyncio
async def test_process_message_triggers_title_generation_beyond_second_turn(
    tmp_path: Path,
) -> None:
    loop = _make_loop(tmp_path)

    async def _fake_run_agent_loop(initial_messages: list[dict[str, Any]], **kwargs: Any):
        del initial_messages, kwargs
        return "ok", [], [], 0, [], False, []

    loop._run_agent_loop = _fake_run_agent_loop
    loop._maybe_learn_experience = lambda **kwargs: None

    calls = 0

    async def _fake_generate_title(session: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            session.metadata["title"] = "Generated Title"

    loop._generate_session_title = _fake_generate_title

    for idx in range(3):
        msg = InboundMessage(channel="telegram", sender_id="u", chat_id="1", content=f"msg-{idx}")
        out = await loop._process_message(msg)
        assert out is not None
        await asyncio.sleep(0)

    assert calls == 1
