from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import json_repair
from loguru import logger

from bao.agent import shared
from bao.agent.memory import MEMORY_CATEGORIES, MEMORY_CATEGORY_CAPS


async def consolidate_memory(loop: Any, session: Any, archive_all: bool = False) -> None:
    memory = loop.context.memory
    target_last_consolidated = session.last_consolidated
    old_messages, keep_count, target_last_consolidated = _select_messages(
        session,
        archive_all=archive_all,
        memory_window=loop.memory_window,
    )
    if old_messages is None:
        return
    conversation = _conversation_text(old_messages)
    current_memory = _current_memory_text(memory)
    prompt = _consolidation_prompt(current_memory=current_memory, conversation=conversation)
    try:
        provider = loop._utility_provider or loop.provider
        model = loop._utility_model or loop.model
        response = await asyncio.wait_for(
            provider.chat(
                shared.ChatRequest(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a memory consolidation agent. Respond only with valid JSON.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    model=model,
                    temperature=loop.temperature,
                    max_tokens=loop.max_tokens,
                    reasoning_effort=loop.reasoning_effort,
                    service_tier=loop.service_tier,
                    source="utility",
                )
            ),
            timeout=90,
        )
        await _apply_consolidation_result(
            ConsolidationApplyRequest(
                loop=loop,
                session=session,
                memory=memory,
                response_content=response.content or "",
                current_memory=current_memory,
                archive_all=archive_all,
                target_last_consolidated=target_last_consolidated,
            )
        )
        logger.info(
            "✅ 完成整合 / consolidation done: {} messages, last_consolidated={}",
            len(session.messages),
            session.last_consolidated,
        )
    except Exception as exc:
        logger.error("❌ 记忆整合失败 / consolidation failed: {}", exc)


def _select_messages(session: Any, *, archive_all: bool, memory_window: int) -> tuple[list[dict[str, Any]] | None, int, int]:
    target_last_consolidated = session.last_consolidated
    if archive_all:
        logger.info(
            "🧠 开始整合 / consolidation start: {} total messages archived",
            len(session.messages),
        )
        return session.messages, 0, target_last_consolidated
    keep_count = memory_window // 2
    if len(session.messages) <= keep_count:
        logger.debug(
            "Session {}: No consolidation needed (messages={}, keep={})",
            session.key,
            len(session.messages),
            keep_count,
        )
        return None, keep_count, target_last_consolidated
    messages_to_process = len(session.messages) - session.last_consolidated
    if messages_to_process <= 0:
        logger.debug(
            "Session {}: No new messages to consolidate (last_consolidated={}, total={})",
            session.key,
            session.last_consolidated,
            len(session.messages),
        )
        return None, keep_count, target_last_consolidated
    snapshot_total = len(session.messages)
    snapshot_stop = max(session.last_consolidated, snapshot_total - keep_count)
    old_messages = session.messages[session.last_consolidated : snapshot_stop]
    if not old_messages:
        return None, keep_count, target_last_consolidated
    logger.info(
        "🧠 开始整合 / consolidation start: {} total, {} new to consolidate, {} keep",
        len(session.messages),
        len(old_messages),
        keep_count,
    )
    return old_messages, keep_count, snapshot_stop


def _conversation_text(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for message in messages:
        if not message.get("content"):
            continue
        tools = f" [tools: {', '.join(message['tools_used'])}]" if message.get("tools_used") else ""
        lines.append(
            f"[{message.get('timestamp', '?')[:16]}] {message['role'].upper()}{tools}: {message['content']}"
        )
    return "\n".join(lines)


def _current_memory_text(memory: Any) -> str:
    parts: list[str] = []
    for category in MEMORY_CATEGORIES:
        category_memory = memory.read_long_term(category).strip()
        parts.append(f"### {category}\n{category_memory or '(empty)'}")
    return "\n\n".join(parts)


def _consolidation_prompt(*, current_memory: str, conversation: str) -> str:
    caps_text = "\n".join(
        f'   - "{category}": <= {MEMORY_CATEGORY_CAPS[category]} chars'
        for category in MEMORY_CATEGORIES
    )
    return f"""You are a memory consolidation agent. Process this conversation and return a JSON object with exactly two keys:

1. "history_entry": A paragraph (2-5 sentences) summarizing key events/decisions/topics. Start with a timestamp like [YYYY-MM-DD HH:MM].

2. "memory_updates": An object where keys are memory categories and values are the FINAL merged content for that category.

Memory categories:
   - "preference": User preferences, habits, communication style, likes/dislikes
   - "personal": User identity, location, relationships, personal facts
   - "project": Project context, technical decisions, tools/services, codebase info
   - "general": Other durable facts that don't fit above categories

Hard caps per category:
{caps_text}

Rules for memory_updates:
   - Merge with existing memory; do not blindly append duplicates.
   - Keep only durable facts. Remove stale or contradictory items.
   - Values must contain ONLY category content. Do NOT include headings like "### preference" or markers like "[preference]".
   - You may set a category to "" to intentionally clear it.
   - ONLY memorize facts that are likely useful across multiple future sessions.
   - DO NOT memorize: transient chat content, debugging details, one-off commands, temporary file paths, or emotional reactions.
   - DO NOT memorize anything already covered by PERSONA.md (name, role, location, language — these are static profile).
   - If a fact is already present in existing memory with equivalent meaning, do NOT add a rephrased duplicate.
   - When in doubt, prefer NOT writing over writing — false negatives are cheaper than noise.

## Current Long-term Memory (by category)
{current_memory}

## Conversation to Process
{conversation}

Respond with ONLY valid JSON, no markdown fences."""


async def _apply_consolidation_result(request: "ConsolidationApplyRequest") -> None:
    text = request.response_content.strip()
    if not text:
        logger.warning("⚠️ 整合结果为空 / empty response: memory consolidation skipped")
        return
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    result = json_repair.loads(text)
    if not isinstance(result, dict):
        logger.warning("⚠️ 整合返回异常 / unexpected response: {}", text[:200])
        return
    history_entry = result.get("history_entry")
    if history_entry:
        if not isinstance(history_entry, str):
            history_entry = json.dumps(history_entry, ensure_ascii=False)
        await asyncio.to_thread(request.memory.append_history, history_entry)
    updates = result.get("memory_updates")
    if isinstance(updates, dict):
        await asyncio.to_thread(request.memory.write_categorized_memory, updates)
    else:
        update = result.get("memory_update")
        if update:
            if not isinstance(update, str):
                update = json.dumps(update, ensure_ascii=False)
            if update != request.current_memory:
                await asyncio.to_thread(request.memory.write_long_term, update)
    if request.archive_all:
        return
    request.session.last_consolidated = request.target_last_consolidated
    request.loop.sessions.save(request.session)


@dataclass(slots=True)
class ConsolidationApplyRequest:
    loop: Any
    session: Any
    memory: Any
    response_content: str
    current_memory: str
    archive_all: bool
    target_last_consolidated: int
