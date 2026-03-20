from __future__ import annotations

from pathlib import Path

from bao.agent import plan
from tests._plan_testkit import make_loop


def test_new_plan_normalizes_and_limits() -> None:
    long_step = "x" * 300
    steps = [f"{index}. [pending] step-{index}-{long_step}" for index in range(1, 15)]
    state = plan.new_plan("goal", steps)
    assert state["schema_version"] == 1
    assert len(state["steps"]) == plan.PLAN_MAX_STEPS
    assert state["steps"][0].startswith("1. [pending] ")
    assert len(state["steps"][0]) <= len("1. [pending] ") + plan.PLAN_MAX_STEP_CHARS
    assert state["current_step"] == 1


def test_format_plan_for_prompt_budget() -> None:
    steps = [f"step {index} " + ("a" * 180) for index in range(1, 11)]
    text = plan.format_plan_for_prompt(plan.new_plan("very long goal " + ("b" * 200), steps))
    assert text.startswith("## Current Plan")
    assert len(text) <= plan.PLAN_MAX_PROMPT_CHARS


def test_done_plan_stops_injection() -> None:
    state = plan.set_step_status(plan.new_plan("goal", ["one"]), 1, plan.STATUS_DONE)
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
    text = plan.format_plan_for_channel(plan.new_plan("goal", ["step"]), lang="zh", channel="slack")
    assert "**当前计划**" in text


def test_is_plan_done_considers_steps_beyond_prompt_cap() -> None:
    state = plan.new_plan("goal", [f"step-{index}" for index in range(1, 11)])
    state["steps"] = [*state["steps"], "11. [pending] hidden tail"]
    assert not plan.is_plan_done(state)


def test_resolve_session_language_isolated_per_session(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    session_zh = loop.sessions.get_or_create("telegram:zh")
    session_en = loop.sessions.get_or_create("telegram:en")
    lang_zh, changed_zh = loop._resolve_session_language(session_zh, "你好，帮我做计划")
    lang_en, changed_en = loop._resolve_session_language(session_en, "Please make a plan")
    assert changed_zh is True and changed_en is True
    assert lang_zh == "zh" and lang_en == "en"
    assert session_zh.metadata.get("_session_lang") == "zh"
    assert session_en.metadata.get("_session_lang") == "en"


def test_resolve_session_language_does_not_persist_ambiguous_fallback(tmp_path: Path) -> None:
    loop = make_loop(tmp_path)
    session = loop.sessions.get_or_create("telegram:amb")
    lang, changed = loop._resolve_session_language(session, "123🙂")
    assert lang in ("zh", "en")
    assert changed is False
    assert "_session_lang" not in session.metadata
