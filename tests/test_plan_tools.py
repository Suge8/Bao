from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from pathlib import Path

from bao.agent import plan
from tests._plan_testkit import make_loop

pytest = importlib.import_module("pytest")


@dataclass(slots=True, frozen=True)
class ToolContextOptions:
    lang: str | None = None
    channel: str = "telegram"
    session_key: str = "telegram:1"
    chat_id: str = "1"


async def _set_tool_contexts(loop, options: ToolContextOptions = ToolContextOptions()):
    create_tool = loop.tools.get("create_plan")
    update_tool = loop.tools.get("update_plan_step")
    clear_tool = loop.tools.get("clear_plan")
    assert create_tool is not None and update_tool is not None and clear_tool is not None
    create_context = getattr(create_tool, "set_context")
    update_context = getattr(update_tool, "set_context")
    clear_context = getattr(clear_tool, "set_context")
    kwargs = {"session_key": options.session_key}
    if options.lang:
        kwargs["lang"] = options.lang
    create_context(options.channel, options.chat_id, **kwargs)
    update_context(options.channel, options.chat_id, **kwargs)
    clear_context(options.channel, options.chat_id, **kwargs)
    return create_tool, update_tool, clear_tool


@pytest.mark.asyncio
async def test_create_plan_tool_persists_metadata(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    create_tool, _, _ = await _set_tool_contexts(loop)
    out = await create_tool.execute(goal="Ship feature", steps=["Analyze", "Implement"])
    assert out.startswith("Plan created:")
    state = loop.sessions.get_or_create("telegram:1").metadata.get(plan.PLAN_STATE_KEY)
    assert isinstance(state, dict)
    assert state.get("goal") == "Ship feature"
    assert len(state.get("steps", [])) == 2


@pytest.mark.asyncio
async def test_create_plan_tool_sends_localized_outbound_message(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    create_tool, _, _ = await _set_tool_contexts(loop, ToolContextOptions(lang="zh"))
    await create_tool.execute(goal="发布功能", steps=["分析", "实现"])
    outbound = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)
    assert outbound.channel == "telegram"
    assert outbound.metadata.get("_plan") is True
    assert outbound.metadata.get("plan_action") == "create"
    assert "**当前计划**" in outbound.content
    assert "**待办** - 分析" in outbound.content
    assert "[pending]" not in outbound.content


@pytest.mark.asyncio
async def test_create_plan_tool_sends_plain_text_for_non_markdown_channel(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    create_tool, _, _ = await _set_tool_contexts(
        loop,
        ToolContextOptions(lang="zh", channel="qq", session_key="qq:1"),
    )
    await create_tool.execute(goal="发布功能", steps=["分析", "实现"])
    outbound = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)
    assert outbound.channel == "qq"
    assert outbound.metadata.get("_plan") is True
    assert "当前计划" in outbound.content
    assert "待办 - 分析" in outbound.content
    assert "**" not in outbound.content


@pytest.mark.asyncio
async def test_update_plan_and_clear_tool_flows(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    create_tool, update_tool, clear_tool = await _set_tool_contexts(loop)
    await create_tool.execute(goal="goal", steps=["step1", "step2"])
    updated = await update_tool.execute(step_index=1, status="done")
    assert updated.startswith("Plan updated:")
    state = loop.sessions.get_or_create("telegram:1").metadata[plan.PLAN_STATE_KEY]
    assert state["current_step"] == 2
    assert "[done]" in state["steps"][0]

    cleared = await clear_tool.execute()
    assert cleared.startswith("Plan cleared")
    assert plan.PLAN_STATE_KEY not in loop.sessions.get_or_create("telegram:1").metadata


@pytest.mark.asyncio
async def test_update_plan_step_auto_archives_on_done(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    create_tool, update_tool, _ = await _set_tool_contexts(loop)
    await create_tool.execute(goal="goal", steps=["step1"])
    out = await update_tool.execute(step_index=1, status="done")
    assert "Archived:" in out
    assert isinstance(loop.sessions.get_or_create("telegram:1").metadata.get(plan.PLAN_ARCHIVED_KEY), str)


@pytest.mark.asyncio
async def test_update_plan_step_sends_localized_outbound_message(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    create_tool, update_tool, _ = await _set_tool_contexts(loop, ToolContextOptions(lang="zh"))
    await create_tool.execute(goal="发布功能", steps=["分析", "实现"])
    _ = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)
    await update_tool.execute(step_index=1, status="done")
    outbound = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)
    assert outbound.metadata.get("_plan") is True
    assert outbound.metadata.get("plan_action") == "update"
    assert "**当前计划**" in outbound.content
    assert "**完成** - 分析" in outbound.content
    assert "**已完成**" not in outbound.content
    assert "[done]" not in outbound.content


@pytest.mark.asyncio
async def test_update_plan_step_idempotent_skips_duplicate_notify(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    create_tool, update_tool, _ = await _set_tool_contexts(loop, ToolContextOptions(lang="en"))
    await create_tool.execute(goal="goal", steps=["step1"])
    _ = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)
    await update_tool.execute(step_index=1, status="done")
    _ = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)
    out = await update_tool.execute(step_index=1, status="done")
    assert out.startswith("Plan unchanged:")
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.2)


@pytest.mark.asyncio
async def test_clear_plan_tool_markdown_notification_for_telegram(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    create_tool, _, clear_tool = await _set_tool_contexts(loop, ToolContextOptions(lang="zh"))
    await create_tool.execute(goal="目标", steps=["步骤一"])
    _ = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)
    out = await clear_tool.execute()
    outbound = await asyncio.wait_for(loop.bus.consume_outbound(), timeout=0.5)
    assert out.startswith("计划已清空")
    assert outbound.metadata.get("_plan") is True
    assert outbound.metadata.get("plan_action") == "clear"
    assert "**计划已清空**" in outbound.content


@pytest.mark.asyncio
async def test_invalid_tool_inputs_and_empty_plan_cases(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    create_tool, update_tool, clear_tool = await _set_tool_contexts(loop)

    out = await create_tool.execute(goal="Ship feature", steps=["Analyze", "   "])
    assert out == "Error: each step must be a non-empty string"

    out = await clear_tool.execute()
    assert out == "No active plan to clear."

    loop = make_loop(tmp_path)
    _, _, clear_tool = await _set_tool_contexts(loop, ToolContextOptions(lang="zh"))
    out = await clear_tool.execute()
    assert out in {"当前没有可清空的计划。", "计划已清空。"}


@pytest.mark.asyncio
async def test_range_and_bool_validation(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    create_tool, update_tool, clear_tool = await _set_tool_contexts(loop)
    await create_tool.execute(goal="goal", steps=["step1"])
    assert (await update_tool.execute(step_index=2, status="done")).startswith(
        "Error: step_index out of range"
    )
    assert await update_tool.execute(step_index=True, status="done") == "Error: step_index must be an integer"

    loop = make_loop(tmp_path)
    create_tool, update_tool, clear_tool = await _set_tool_contexts(loop)
    await create_tool.execute(goal="goal", steps=["step1", "contains [done] literal"])
    assert (await update_tool.execute(step_index=1, status="done")).startswith("Plan updated: 1/2 done")

    session = loop.sessions.get_or_create("telegram:1")
    session.metadata[plan.PLAN_STATE_KEY] = {}
    loop.sessions.save(session)
    out = await clear_tool.execute()
    assert out.startswith("Plan cleared")
    assert plan.PLAN_STATE_KEY not in loop.sessions.get_or_create("telegram:1").metadata
