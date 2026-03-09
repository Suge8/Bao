from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
from unittest.mock import MagicMock

from bao.agent import plan
from bao.agent.context import ContextBuilder
from bao.agent.loop import AgentLoop
from bao.bus.events import InboundMessage
from bao.bus.queue import MessageBus

pytest = importlib.import_module("pytest")


def _make_loop(tmp_path: Path) -> AgentLoop:
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    return AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path, model="test-model")


@pytest.mark.unit
@pytest.mark.smoke
def test_new_plan_normalizes_and_limits() -> None:
    long_step = "x" * 300
    steps = [f"{i}. [pending] step-{i}-{long_step}" for i in range(1, 15)]
    state = plan.new_plan("goal", steps)

    assert state["schema_version"] == 1
    assert len(state["steps"]) == plan.PLAN_MAX_STEPS
    assert state["steps"][0].startswith("1. [pending] ")
    assert len(state["steps"][0]) <= (len("1. [pending] ") + plan.PLAN_MAX_STEP_CHARS)
    assert state["current_step"] == 1


def test_format_plan_for_prompt_budget() -> None:
    steps = [f"step {i} " + ("a" * 180) for i in range(1, 11)]
    state = plan.new_plan("very long goal " + ("b" * 200), steps)
    text = plan.format_plan_for_prompt(state)

    assert text.startswith("## Current Plan")
    assert len(text) <= plan.PLAN_MAX_PROMPT_CHARS


def test_done_plan_stops_injection() -> None:
    state = plan.new_plan("goal", ["one"])
    state = plan.set_step_status(state, 1, plan.STATUS_DONE)
    assert plan.is_plan_done(state)
    assert plan.format_plan_for_prompt(state) == ""
    assert plan.plan_signal_text(state) == ""


def test_format_plan_for_user_localized_plain_text() -> None:
    state = plan.new_plan("ship feature", ["Analyze", "Implement"])

    en_text = plan.format_plan_for_user(state, lang="en")
    zh_text = plan.format_plan_for_user(state, lang="zh")

    assert "Current plan" in en_text
    assert "Pending - Analyze" in en_text
    assert "[pending]" not in en_text

    assert "当前计划" in zh_text
    assert "待办 - Analyze" in zh_text
    assert "[pending]" not in zh_text


def test_format_plan_for_channel_splits_markdown_and_plain() -> None:
    state = plan.new_plan("ship feature", ["Analyze", "Implement"])

    md_text = plan.format_plan_for_channel(state, lang="zh", channel="telegram")
    lite_md_text = plan.format_plan_for_channel(state, lang="zh", channel="whatsapp")
    plain_text = plan.format_plan_for_channel(state, lang="zh", channel="qq")

    assert "**当前计划**" in md_text
    assert "**待办** - Analyze" in md_text
    assert "*当前计划*" in lite_md_text
    assert "*待办* - Analyze" in lite_md_text
    assert "**" not in plain_text
    assert "当前计划" in plain_text


def test_format_plan_for_channel_escapes_markdown_sensitive_text() -> None:
    state = plan.new_plan("A*B", ["Use `cmd` [x](y)"])

    md_text = plan.format_plan_for_channel(state, lang="en", channel="telegram")
    plain_text = plan.format_plan_for_channel(state, lang="en", channel="qq")

    assert "A\\*B" in md_text
    assert "Use \\`cmd\\` \\[x\\]\\(y\\)" in md_text
    assert "A*B" in plain_text


def test_slack_uses_full_markdown_mode() -> None:
    state = plan.new_plan("goal", ["step"])
    text = plan.format_plan_for_channel(state, lang="zh", channel="slack")
    assert "**当前计划**" in text


def test_is_plan_done_considers_steps_beyond_prompt_cap() -> None:
    state = plan.new_plan("goal", [f"step-{i}" for i in range(1, 11)])
    raw_steps = list(state["steps"])
    raw_steps.append("11. [pending] hidden tail")
    state["steps"] = raw_steps
    assert not plan.is_plan_done(state)


def test_resolve_session_language_isolated_per_session(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    session_zh = loop.sessions.get_or_create("telegram:zh")
    session_en = loop.sessions.get_or_create("telegram:en")

    lang_zh, changed_zh = loop._resolve_session_language(session_zh, "你好，帮我做计划")
    lang_en, changed_en = loop._resolve_session_language(session_en, "Please make a plan")

    assert changed_zh is True
    assert changed_en is True
    assert lang_zh == "zh"
    assert lang_en == "en"
    assert session_zh.metadata.get("_session_lang") == "zh"
    assert session_en.metadata.get("_session_lang") == "en"


def test_resolve_session_language_does_not_persist_ambiguous_fallback(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    session = loop.sessions.get_or_create("telegram:amb")

    lang, changed = loop._resolve_session_language(session, "123🙂")

    assert lang in ("zh", "en")
    assert changed is False
    assert "_session_lang" not in session.metadata


@pytest.mark.asyncio
async def test_create_plan_tool_persists_metadata(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    tool = loop.tools.get("create_plan")
    assert tool is not None

    set_context = getattr(tool, "set_context", None)
    assert callable(set_context)
    set_context("telegram", "1", session_key="telegram:1")

    out = await tool.execute(goal="Ship feature", steps=["Analyze", "Implement"])
    assert out.startswith("Plan created:")

    session = loop.sessions.get_or_create("telegram:1")
    state = session.metadata.get(plan.PLAN_STATE_KEY)
    assert isinstance(state, dict)
    assert state.get("goal") == "Ship feature"
    assert len(state.get("steps", [])) == 2


@pytest.mark.asyncio
async def test_create_plan_tool_sends_localized_outbound_message(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    tool = loop.tools.get("create_plan")
    assert tool is not None

    set_context = getattr(tool, "set_context", None)
    assert callable(set_context)
    set_context("telegram", "1", session_key="telegram:1", lang="zh")

    await tool.execute(goal="发布功能", steps=["分析", "实现"])
    outbound = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)

    assert outbound.channel == "telegram"
    assert outbound.chat_id == "1"
    assert outbound.metadata.get("_plan") is True
    assert outbound.metadata.get("plan_action") == "create"
    assert "**当前计划**" in outbound.content
    assert "**待办** - 分析" in outbound.content
    assert "[pending]" not in outbound.content


@pytest.mark.asyncio
async def test_create_plan_tool_sends_plain_text_for_non_markdown_channel(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    tool = loop.tools.get("create_plan")
    assert tool is not None

    set_context = getattr(tool, "set_context", None)
    assert callable(set_context)
    set_context("qq", "1", session_key="qq:1", lang="zh")

    await tool.execute(goal="发布功能", steps=["分析", "实现"])
    outbound = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)

    assert outbound.channel == "qq"
    assert outbound.metadata.get("_plan") is True
    assert "当前计划" in outbound.content
    assert "待办 - 分析" in outbound.content
    assert "**" not in outbound.content


@pytest.mark.asyncio
async def test_create_plan_tool_preserves_slack_thread_metadata(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    tool = loop.tools.get("create_plan")
    assert tool is not None

    set_context = getattr(tool, "set_context", None)
    assert callable(set_context)
    set_context(
        "slack",
        "C123",
        session_key="slack:C123:1710000000.1234",
        lang="en",
        reply_metadata={
            "slack": {
                "thread_ts": "1710000000.1234",
                "channel_type": "channel",
                "event": {"ignored": True},
            }
        },
    )

    await tool.execute(goal="Ship", steps=["Step 1"])
    outbound = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)

    slack_meta = outbound.metadata.get("slack")
    assert isinstance(slack_meta, dict)
    assert slack_meta.get("thread_ts") == "1710000000.1234"
    assert slack_meta.get("channel_type") == "channel"
    assert "event" not in slack_meta


@pytest.mark.asyncio
async def test_update_plan_step_advances_pointer(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    create_tool = loop.tools.get("create_plan")
    update_tool = loop.tools.get("update_plan_step")
    assert create_tool is not None and update_tool is not None

    create_set_context = getattr(create_tool, "set_context")
    update_set_context = getattr(update_tool, "set_context")
    create_set_context("telegram", "1", session_key="telegram:1")
    update_set_context("telegram", "1", session_key="telegram:1")

    await create_tool.execute(goal="goal", steps=["step1", "step2"])
    out = await update_tool.execute(step_index=1, status="done")
    assert out.startswith("Plan updated:")

    state = loop.sessions.get_or_create("telegram:1").metadata[plan.PLAN_STATE_KEY]
    assert state["current_step"] == 2
    assert "[done]" in state["steps"][0]


@pytest.mark.asyncio
async def test_update_plan_step_auto_archives_on_done(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    create_tool = loop.tools.get("create_plan")
    update_tool = loop.tools.get("update_plan_step")
    assert create_tool is not None and update_tool is not None

    create_set_context = getattr(create_tool, "set_context")
    update_set_context = getattr(update_tool, "set_context")
    create_set_context("telegram", "1", session_key="telegram:1")
    update_set_context("telegram", "1", session_key="telegram:1")

    await create_tool.execute(goal="goal", steps=["step1"])
    out = await update_tool.execute(step_index=1, status="done")
    assert "Archived:" in out

    session = loop.sessions.get_or_create("telegram:1")
    assert isinstance(session.metadata.get(plan.PLAN_ARCHIVED_KEY), str)


@pytest.mark.asyncio
async def test_update_plan_step_sends_localized_outbound_message(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    create_tool = loop.tools.get("create_plan")
    update_tool = loop.tools.get("update_plan_step")
    assert create_tool is not None and update_tool is not None

    create_set_context = getattr(create_tool, "set_context")
    update_set_context = getattr(update_tool, "set_context")
    create_set_context("telegram", "1", session_key="telegram:1", lang="zh")
    update_set_context("telegram", "1", session_key="telegram:1", lang="zh")

    await create_tool.execute(goal="发布功能", steps=["分析", "实现"])
    _ = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)

    await update_tool.execute(step_index=1, status="done")
    outbound = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)

    assert outbound.channel == "telegram"
    assert outbound.chat_id == "1"
    assert outbound.metadata.get("_plan") is True
    assert outbound.metadata.get("plan_action") == "update"
    assert "**当前计划**" in outbound.content
    assert "**完成** - 分析" in outbound.content
    assert "**已完成**" not in outbound.content
    assert "[done]" not in outbound.content


@pytest.mark.asyncio
async def test_update_plan_step_idempotent_skips_duplicate_notify(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    create_tool = loop.tools.get("create_plan")
    update_tool = loop.tools.get("update_plan_step")
    assert create_tool is not None and update_tool is not None

    create_set_context = getattr(create_tool, "set_context")
    update_set_context = getattr(update_tool, "set_context")
    create_set_context("telegram", "1", session_key="telegram:1", lang="en")
    update_set_context("telegram", "1", session_key="telegram:1", lang="en")

    await create_tool.execute(goal="goal", steps=["step1"])
    _ = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)

    await update_tool.execute(step_index=1, status="done")
    _ = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)

    out = await update_tool.execute(step_index=1, status="done")
    assert out.startswith("Plan unchanged:")
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.2)


@pytest.mark.asyncio
async def test_clear_plan_tool(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    create_tool = loop.tools.get("create_plan")
    clear_tool = loop.tools.get("clear_plan")
    assert create_tool is not None and clear_tool is not None

    create_set_context = getattr(create_tool, "set_context")
    clear_set_context = getattr(clear_tool, "set_context")
    create_set_context("telegram", "1", session_key="telegram:1")
    clear_set_context("telegram", "1", session_key="telegram:1")

    await create_tool.execute(goal="goal", steps=["step1"])
    out = await clear_tool.execute()
    assert out.startswith("Plan cleared")

    session = loop.sessions.get_or_create("telegram:1")
    assert plan.PLAN_STATE_KEY not in session.metadata


@pytest.mark.asyncio
async def test_clear_plan_tool_markdown_notification_for_telegram(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    create_tool = loop.tools.get("create_plan")
    clear_tool = loop.tools.get("clear_plan")
    assert create_tool is not None and clear_tool is not None

    create_set_context = getattr(create_tool, "set_context")
    clear_set_context = getattr(clear_tool, "set_context")
    create_set_context("telegram", "1", session_key="telegram:1", lang="zh")
    clear_set_context("telegram", "1", session_key="telegram:1", lang="zh")

    await create_tool.execute(goal="目标", steps=["步骤一"])
    _ = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)
    out = await clear_tool.execute()
    outbound = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)

    assert out.startswith("计划已清空")
    assert outbound.metadata.get("_plan") is True
    assert outbound.metadata.get("plan_action") == "clear"
    assert "**计划已清空**" in outbound.content


@pytest.mark.asyncio
async def test_update_plan_step_rejects_out_of_range_index(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    create_tool = loop.tools.get("create_plan")
    update_tool = loop.tools.get("update_plan_step")
    assert create_tool is not None and update_tool is not None

    create_set_context = getattr(create_tool, "set_context")
    update_set_context = getattr(update_tool, "set_context")
    create_set_context("telegram", "1", session_key="telegram:1")
    update_set_context("telegram", "1", session_key="telegram:1")

    await create_tool.execute(goal="goal", steps=["step1"])
    out = await update_tool.execute(step_index=2, status="done")
    assert out.startswith("Error: step_index out of range")


@pytest.mark.asyncio
async def test_create_plan_rejects_blank_steps_after_validation(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    tool = loop.tools.get("create_plan")
    assert tool is not None

    set_context = getattr(tool, "set_context", None)
    assert callable(set_context)
    set_context("telegram", "1", session_key="telegram:1")

    out = await tool.execute(goal="Ship feature", steps=["Analyze", "   "])
    assert out == "Error: each step must be a non-empty string"


@pytest.mark.asyncio
async def test_clear_plan_tool_without_active_plan(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    clear_tool = loop.tools.get("clear_plan")
    assert clear_tool is not None

    clear_set_context = getattr(clear_tool, "set_context")
    clear_set_context("telegram", "1", session_key="telegram:1")

    out = await clear_tool.execute()
    assert out == "No active plan to clear."


@pytest.mark.asyncio
async def test_clear_plan_tool_without_active_plan_zh_no_outbound(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    clear_tool = loop.tools.get("clear_plan")
    assert clear_tool is not None

    clear_set_context = getattr(clear_tool, "set_context")
    clear_set_context("telegram", "1", session_key="telegram:1", lang="zh")

    out = await clear_tool.execute()
    assert out == "当前没有可清空的计划。"
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.2)


@pytest.mark.asyncio
async def test_clear_plan_tool_handles_falsy_plan_state(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    clear_tool = loop.tools.get("clear_plan")
    assert clear_tool is not None

    session = loop.sessions.get_or_create("telegram:1")
    session.metadata[plan.PLAN_STATE_KEY] = {}
    loop.sessions.save(session)

    clear_set_context = getattr(clear_tool, "set_context")
    clear_set_context("telegram", "1", session_key="telegram:1")

    out = await clear_tool.execute()
    assert out.startswith("Plan cleared")
    refreshed = loop.sessions.get_or_create("telegram:1")
    assert plan.PLAN_STATE_KEY not in refreshed.metadata


@pytest.mark.asyncio
async def test_update_plan_step_rejects_bool_index(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    create_tool = loop.tools.get("create_plan")
    update_tool = loop.tools.get("update_plan_step")
    assert create_tool is not None and update_tool is not None

    create_set_context = getattr(create_tool, "set_context")
    update_set_context = getattr(update_tool, "set_context")
    create_set_context("telegram", "1", session_key="telegram:1")
    update_set_context("telegram", "1", session_key="telegram:1")

    await create_tool.execute(goal="goal", steps=["step1"])
    out = await update_tool.execute(step_index=True, status="done")
    assert out == "Error: step_index must be an integer"


@pytest.mark.asyncio
async def test_update_plan_step_done_count_ignores_body_literal(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    create_tool = loop.tools.get("create_plan")
    update_tool = loop.tools.get("update_plan_step")
    assert create_tool is not None and update_tool is not None

    create_set_context = getattr(create_tool, "set_context")
    update_set_context = getattr(update_tool, "set_context")
    create_set_context("telegram", "1", session_key="telegram:1")
    update_set_context("telegram", "1", session_key="telegram:1")

    await create_tool.execute(goal="goal", steps=["step1", "contains [done] literal"])
    out = await update_tool.execute(step_index=1, status="done")
    assert out.startswith("Plan updated: 1/2 done")


@pytest.mark.integration
@pytest.mark.smoke
def test_plan_injected_before_memory(tmp_path: Path) -> None:
    ctx = ContextBuilder(tmp_path)
    state = plan.new_plan("goal", ["step1", "step2"])

    messages = ctx.build_messages(
        history=[],
        current_message="hello",
        related_memory=["m1"],
        related_experience=["e1"],
        plan_state=state,
        model="test-model",
    )
    system = messages[0]["content"]

    idx_plan = system.find("## Current Plan")
    idx_memory = system.find("## Related Memory")
    assert idx_plan != -1
    assert idx_memory != -1
    assert idx_plan < idx_memory


def test_done_plan_not_injected(tmp_path: Path) -> None:
    ctx = ContextBuilder(tmp_path)
    state = plan.new_plan("goal", ["step1"])
    state = plan.set_step_status(state, 1, plan.STATUS_DONE)

    messages = ctx.build_messages(
        history=[],
        current_message="hello",
        related_memory=["m1"],
        plan_state=state,
        model="test-model",
    )
    system = messages[0]["content"]
    assert "## Current Plan" not in system


def test_tool_exposure_auto_includes_code_tools_when_plan_mentions_code(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    loop._tool_exposure_mode = "auto"
    loop._tool_exposure_bundles = {"core", "code", "web", "desktop"}

    initial_messages = [
        {"role": "system", "content": "test"},
        {"role": "user", "content": "hello"},
    ]

    selected = loop._select_tool_names_for_turn(
        initial_messages,
        extra_signal_text="write python script and run test",
    )
    assert isinstance(selected, set)
    assert "read_file" in selected
    assert "exec" in selected


def test_tool_exposure_signal_does_not_mutate_prompt_messages(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    loop._tool_exposure_mode = "auto"
    loop._tool_exposure_bundles = {"core", "code", "web", "desktop"}
    marker = "__plan_signal_marker__"
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
    ]
    before = [dict(m) for m in messages]

    _ = loop._select_tool_names_for_turn(messages, extra_signal_text=marker)

    assert messages == before
    assert marker not in str(messages[0].get("content", ""))


def test_plan_tools_always_registered(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    assert loop.tools.has("create_plan")
    assert loop.tools.has("update_plan_step")
    assert loop.tools.has("clear_plan")


def test_help_command_does_not_expose_plan_command(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    msg = InboundMessage(channel="telegram", sender_id="u", chat_id="1", content="/help")

    out = asyncio.run(loop._process_message(msg))
    assert out is not None
    assert "/plan" not in out.content


def test_planning_tool_metadata_contains_trigger_policy(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    create_meta = loop.tools.get_metadata("create_plan")
    update_meta = loop.tools.get_metadata("update_plan_step")
    clear_meta = loop.tools.get_metadata("clear_plan")
    assert create_meta is not None
    assert update_meta is not None
    assert clear_meta is not None
    assert "2+ meaningful steps" in create_meta.short_hint
    assert "progress" in update_meta.short_hint.lower()
    assert "done" in clear_meta.short_hint.lower() or "abandoned" in clear_meta.short_hint.lower()
