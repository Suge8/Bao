from __future__ import annotations

import asyncio
from pathlib import Path

from bao.agent import plan
from bao.agent.context import BuildMessagesRequest, ContextBuilder
from bao.bus.events import InboundMessage
from tests._plan_testkit import make_loop


def test_plan_injected_before_memory(tmp_path: Path) -> None:
    ctx = ContextBuilder(tmp_path)
    state = plan.new_plan("goal", ["step1", "step2"])
    messages = ctx.build_messages(
        BuildMessagesRequest(
            history=[],
            current_message="hello",
            related_memory=["m1"],
            related_experience=["e1"],
            plan_state=state,
            model="test-model",
        )
    )
    system = messages[0]["content"]
    assert system.find("## Current Plan") < system.find("## Related Memory")


def test_done_plan_not_injected(tmp_path: Path) -> None:
    ctx = ContextBuilder(tmp_path)
    state = plan.set_step_status(plan.new_plan("goal", ["step1"]), 1, plan.STATUS_DONE)
    messages = ctx.build_messages(
        BuildMessagesRequest(
            history=[],
            current_message="hello",
            related_memory=["m1"],
            plan_state=state,
            model="test-model",
        )
    )
    assert "## Current Plan" not in messages[0]["content"]


def test_tool_exposure_auto_includes_code_tools_when_plan_mentions_code(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    loop._tool_exposure_mode = "auto"
    loop._tool_exposure_domains = {
        "core",
        "messaging",
        "handoff",
        "web_research",
        "desktop_automation",
        "coding_backend",
    }
    selected = loop._select_tool_names_for_turn(
        [{"role": "system", "content": "test"}, {"role": "user", "content": "hello"}],
        extra_signal_text="write python script and run test",
    )
    assert isinstance(selected, set)
    assert "read_file" in selected
    assert "exec" in selected


def test_tool_exposure_signal_does_not_mutate_prompt_messages(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    loop._tool_exposure_mode = "auto"
    loop._tool_exposure_domains = {
        "core",
        "messaging",
        "handoff",
        "web_research",
        "desktop_automation",
        "coding_backend",
    }
    marker = "__plan_signal_marker__"
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hello"}]
    before = [dict(message) for message in messages]
    _ = loop._select_tool_names_for_turn(messages, extra_signal_text=marker)
    assert messages == before
    assert marker not in str(messages[0].get("content", ""))


def test_plan_tools_always_registered(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    assert loop.tools.has("create_plan")
    assert loop.tools.has("update_plan_step")
    assert loop.tools.has("clear_plan")


def test_help_command_does_not_expose_plan_command(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    out = asyncio.run(loop._process_message(InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="/help")))
    assert out is not None
    assert "/plan" not in out.content


def test_planning_tool_metadata_contains_trigger_policy(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    create_meta = loop.tools.get_metadata("create_plan")
    update_meta = loop.tools.get_metadata("update_plan_step")
    clear_meta = loop.tools.get_metadata("clear_plan")
    assert create_meta is not None and update_meta is not None and clear_meta is not None
    assert "2+ meaningful steps" in create_meta.short_hint
    assert "progress" in update_meta.short_hint.lower()
    assert "done" in clear_meta.short_hint.lower() or "abandoned" in clear_meta.short_hint.lower()
