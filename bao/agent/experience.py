"""Experience engine: learning extraction and merge/cleanup.

Extracted from loop.py to isolate background experience tasks from the
main message loop.  Both functions are fire-and-forget async tasks
launched via asyncio.create_task in AgentLoop._maybe_learn_experience.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from loguru import logger

if TYPE_CHECKING:
    from bao.agent.memory import MemoryStore

# Callback signature matching AgentLoop._call_utility_llm
UtilityLLMFn = Callable[[str, str], Awaitable[dict[str, Any] | None]]


@dataclass(frozen=True)
class ExperienceSummaryRequest:
    memory: MemoryStore
    llm_fn: UtilityLLMFn
    user_request: str
    final_response: str
    tools_used: list[str]
    tool_trace: list[str]
    total_errors: int = 0
    reasoning_snippets: list[str] | None = None


def _build_experience_summary_prompt(request: ExperienceSummaryRequest) -> tuple[str, str]:
    tools_str = ", ".join(dict.fromkeys(request.tools_used))
    trace_str = " → ".join(request.tool_trace) if request.tool_trace else "none"
    reasoning_str = (
        " | ".join(request.reasoning_snippets[:5]) if request.reasoning_snippets else "none"
    )
    prompt = f"""Analyze this completed task and extract reusable lessons. Return a JSON object with exactly six keys:

1. "task": One-sentence description of what the user asked for (max 80 chars)
2. "outcome": "success" or "partial" or "failed"
3. "quality": Integer 1-5 rating of how useful this experience would be for future similar tasks (5=highly reusable strategy, 1=trivial or too specific)
4. "category": One of: "coding", "search", "file", "config", "analysis", "general"
5. "lessons": 1-3 sentences of actionable lessons learned — what worked, what didn't, what to do differently next time. For successful tasks, also extract the winning strategy that should be reused. Focus on strategies and patterns, not task-specific details.
6. "keywords": 2-5 short keywords/phrases for future retrieval, comma-separated (e.g. "git rebase, merge conflict, branch cleanup")

If the task was trivial (simple greeting, factual Q&A, no real problem-solving), return {{"skip": true}}.

## User Request
{request.user_request[:500]}

## Tools Used
{tools_str}

## Execution Trace
{trace_str}

## Reasoning Steps
{reasoning_str[:600]}

## Final Response (truncated)
{request.final_response[:800]}

Respond with ONLY valid JSON, no markdown fences."""
    return prompt, reasoning_str


async def _persist_experience_summary(
    request: ExperienceSummaryRequest,
    result: dict[str, Any],
    reasoning_trace: str,
) -> None:
    task = result.get("task", "")
    lessons = result.get("lessons", "")
    if not (task and lessons):
        return
    outcome = result.get("outcome", "unknown")
    quality = max(1, min(5, int(result.get("quality", 3))))
    category = result.get("category", "general")
    keywords = result.get("keywords", "")
    await asyncio.to_thread(
        request.memory.append_experience,
        task,
        outcome,
        lessons,
        quality=quality,
        category=category,
        keywords=keywords,
        reasoning_trace=reasoning_trace,
    )
    logger.info(
        "📝 提取经验 / extracting experience: {} [{}] q={} cat={}",
        task[:60],
        outcome,
        quality,
        category,
    )
    if outcome == "failed":
        await asyncio.to_thread(request.memory.deprecate_similar, task)
    elif request.total_errors == 0:
        await asyncio.to_thread(request.memory.record_reuse, task, True)


async def summarize_experience(request: ExperienceSummaryRequest) -> None:
    """Extract reusable lessons from a completed task."""
    prompt, reasoning_str = _build_experience_summary_prompt(request)

    try:
        result = await request.llm_fn(
            "You are an experience extraction agent. Respond only with valid JSON.", prompt
        )
        if not result or result.get("skip"):
            return
        reasoning_trace = reasoning_str[:300] if request.reasoning_snippets else ""
        await _persist_experience_summary(request, result, reasoning_trace)
    except Exception as e:
        logger.debug("Experience extraction skipped: {}", e)


async def merge_and_cleanup_experiences(
    memory: MemoryStore,
    llm_fn: UtilityLLMFn,
) -> None:
    """Periodically merge similar experiences and clean up stale ones."""
    try:
        await asyncio.to_thread(memory.cleanup_stale)
        groups = await asyncio.to_thread(memory.get_merge_candidates)
    except Exception as e:
        logger.debug("Experience cleanup skipped: {}", e)
        return
    if not groups:
        return
    for entries in groups[:2]:
        entries_text = "\n---\n".join(entries[:6])
        prompt = f"""Merge these similar experience entries into ONE concise high-level principle. Return a JSON object with:
1. "task": Generalized task description (max 80 chars)
2. "outcome": "success"
3. "quality": 5
4. "category": The shared category
5. "lessons": 2-3 sentences distilling the common pattern/strategy across all entries

## Entries to Merge
{entries_text}

Respond with ONLY valid JSON, no markdown fences."""
        try:
            result = await llm_fn(
                "You are an experience consolidation agent. Respond only with valid JSON.",
                prompt,
            )
            if not result:
                continue
            task, lessons = result.get("task", ""), result.get("lessons", "")
            if not (task and lessons):
                continue
            quality = max(1, min(5, int(result.get("quality", 5))))
            category = result.get("category", "general")
            merged = f"Task: {task}\nLessons: {lessons}"
            await asyncio.to_thread(
                memory.replace_merged, entries[:6], merged, category=category, quality=quality
            )
        except Exception as e:
            logger.debug("Experience merge skipped: {}", e)
