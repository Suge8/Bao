from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bao.agent._plan_constants import (
    LITE_MARKDOWN_CHANNELS,
    MARKDOWN_CHANNELS,
    PLAN_MAX_GOAL_CHARS,
    PLAN_MAX_STEPS,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    STATUS_PENDING,
    STATUS_SKIPPED,
)
from bao.agent._plan_core import clip, extract_steps, next_pending_index, normalize_language


def channel_format_mode(channel: str | None) -> str:
    normalized = str(channel or "").strip().lower()
    if normalized in LITE_MARKDOWN_CHANNELS:
        return "md-lite"
    if normalized in MARKDOWN_CHANNELS:
        return "md"
    return "plain"


def no_active_plan_text(lang: str | None = None) -> str:
    return "当前没有进行中的计划。" if normalize_language(lang) == "zh" else "No active plan."


def no_plan_to_clear_text(lang: str | None = None) -> str:
    return "当前没有可清空的计划。" if normalize_language(lang) == "zh" else "No active plan to clear."


def plan_cleared_text(archived: str | None = None, *, lang: str | None = None) -> str:
    archived_text = archived if isinstance(archived, str) else ""
    if normalize_language(lang) == "zh":
        return f"计划已清空。\n{archived_text}" if archived_text else "计划已清空。"
    return f"Plan cleared.\n{archived_text}" if archived_text else "Plan cleared."


def format_plan_for_user(plan_state: dict[str, Any] | None, lang: str | None = None) -> str:
    language = normalize_language(lang)
    if not isinstance(plan_state, dict):
        return no_active_plan_text(language)
    parsed = extract_steps(plan_state)
    if not parsed:
        return no_active_plan_text(language)
    goal = clip(str(plan_state.get("goal", "")), PLAN_MAX_GOAL_CHARS)
    done_count = sum(1 for status, _body in parsed if status == STATUS_DONE)
    header = _header_lines(
        HeaderRequest(
            lang=language,
            goal=goal,
            done_count=done_count,
            total=len(parsed),
            current=next_pending_index(parsed),
        )
    )
    lines = [f"{idx}. {status_label(status, language)} - {body}" for idx, (status, body) in enumerate(parsed, start=1)]
    return "\n".join([*header, *lines])


def format_plan_for_channel(
    plan_state: dict[str, Any] | None,
    *,
    lang: str | None = None,
    channel: str | None = None,
) -> str:
    mode = channel_format_mode(channel)
    if mode == "plain":
        return format_plan_for_user(plan_state, lang=lang)
    language = normalize_language(lang)
    if not isinstance(plan_state, dict):
        return no_active_plan_text(language)
    parsed = extract_steps(plan_state)
    if not parsed:
        return no_active_plan_text(language)
    goal = escape_for_channel(clip(str(plan_state.get("goal", "")), PLAN_MAX_GOAL_CHARS), mode)
    done_count = sum(1 for status, _body in parsed if status == STATUS_DONE)
    header = _header_lines(
        HeaderRequest(
            lang=language,
            goal=goal,
            done_count=done_count,
            total=len(parsed),
            current=next_pending_index(parsed),
            mode=mode,
        )
    )
    lines = [
        f"{idx}. {emphasis(status_label(status, language), mode)} - {escape_for_channel(body, mode)}"
        for idx, (status, body) in enumerate(parsed, start=1)
    ]
    return "\n".join([*header, *lines])


def archive_plan(plan_state: dict[str, Any] | None, lang: str | None = None) -> str:
    if not isinstance(plan_state, dict):
        return ""
    parsed = extract_steps(plan_state, limit=PLAN_MAX_STEPS)
    if not parsed:
        return ""
    goal = clip(str(plan_state.get("goal", "")), PLAN_MAX_GOAL_CHARS)
    done_count = sum(1 for status, _body in parsed if status == STATUS_DONE)
    if normalize_language(lang) == "zh":
        return f"已完成：{goal}；共 {len(parsed)} 步，完成 {done_count} 步。" if goal else f"计划已完成；共 {len(parsed)} 步，完成 {done_count} 步。"
    return f"Completed: {goal}; {done_count}/{len(parsed)} steps done." if goal else f"Completed plan; {done_count}/{len(parsed)} steps done."


def archive_plan_for_channel(
    plan_state: dict[str, Any] | None,
    *,
    lang: str | None = None,
    channel: str | None = None,
) -> str:
    mode = channel_format_mode(channel)
    if mode == "plain":
        return archive_plan(plan_state, lang=lang)
    if not isinstance(plan_state, dict):
        return ""
    parsed = extract_steps(plan_state, limit=PLAN_MAX_STEPS)
    if not parsed:
        return ""
    goal = escape_for_channel(clip(str(plan_state.get("goal", "")), PLAN_MAX_GOAL_CHARS), mode)
    done_count = sum(1 for status, _body in parsed if status == STATUS_DONE)
    if normalize_language(lang) == "zh":
        return f"{emphasis('已完成', mode)}：{goal}；共 {len(parsed)} 步，完成 {done_count} 步。" if goal else f"{emphasis('计划已完成', mode)}；共 {len(parsed)} 步，完成 {done_count} 步。"
    return f"{emphasis('Completed', mode)}: {goal}; {done_count}/{len(parsed)} steps done." if goal else f"{emphasis('Completed', mode)}: plan; {done_count}/{len(parsed)} steps done."


def plan_cleared_text_for_channel(
    archived: str | None = None,
    *,
    lang: str | None = None,
    channel: str | None = None,
) -> str:
    mode = channel_format_mode(channel)
    if mode == "plain":
        return plan_cleared_text(archived, lang=lang)
    head = f"{emphasis('计划已清空', mode)}。" if normalize_language(lang) == "zh" else f"{emphasis('Plan cleared', mode)}."
    archived_text = archived if isinstance(archived, str) else ""
    return head if not archived_text else f"{head}\n{escape_for_channel(archived_text, mode)}"


def emphasis(text: str, mode: str) -> str:
    if mode == "md":
        return f"**{text}**"
    if mode == "md-lite":
        return f"*{text}*"
    return text


def escape_for_channel(text: str, mode: str) -> str:
    if mode == "plain":
        return text
    escaped = text.replace("\\", "\\\\")
    for token in ("*", "_", "~", "`", "[", "]", "(", ")"):
        escaped = escaped.replace(token, f"\\{token}")
    return escaped


def status_label(status: str, lang: str) -> str:
    labels = {
        "zh": {
            STATUS_PENDING: "待办",
            STATUS_DONE: "完成",
            STATUS_SKIPPED: "跳过",
            STATUS_FAILED: "失败",
            STATUS_INTERRUPTED: "中断",
        },
        "en": {
            STATUS_PENDING: "Pending",
            STATUS_DONE: "Done",
            STATUS_SKIPPED: "Skipped",
            STATUS_FAILED: "Failed",
            STATUS_INTERRUPTED: "Interrupted",
        },
    }
    return labels["zh" if lang == "zh" else "en"].get(status, "待办" if lang == "zh" else "Pending")


@dataclass(frozen=True)
class HeaderRequest:
    lang: str
    goal: str
    done_count: int
    total: int
    current: int
    mode: str = "plain"


def _header_lines(request: HeaderRequest) -> list[str]:
    if request.lang == "zh":
        title = "当前计划"
        goal_line = f"目标：{request.goal}" if request.goal else "目标：（未填写）"
        progress = f"进度：{request.done_count}/{request.total}，当前步骤：{request.current}"
    else:
        title = "Current plan"
        goal_line = f"Goal: {request.goal}" if request.goal else "Goal: (unspecified)"
        progress = f"Progress: {request.done_count}/{request.total}, current step: {request.current}"
    if request.mode != "plain":
        title = emphasis(title, request.mode)
    return [title, goal_line, progress]
