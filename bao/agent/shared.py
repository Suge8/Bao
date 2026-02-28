"""Shared utilities for AgentLoop and SubagentManager.

Extracted to eliminate duplication between loop.py and subagent.py.
Both classes retain thin wrapper methods that delegate here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable

import json_repair
from loguru import logger

if TYPE_CHECKING:
    from bao.agent.artifacts import ArtifactStore


# ---------------------------------------------------------------------------
# 1. parse_llm_json — pure function, no deps
# ---------------------------------------------------------------------------


def parse_llm_json(content: str | None) -> dict[str, Any] | None:
    """Parse LLM response as JSON, tolerating markdown fences."""
    text = (content or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    result = json_repair.loads(text)
    return result if isinstance(result, dict) else None


# ---------------------------------------------------------------------------
# 2. call_experience_llm — async, provider info passed explicitly
# ---------------------------------------------------------------------------


async def call_experience_llm(
    system: str,
    prompt: str,
    *,
    experience_mode: str | None,
    provider: Any,
    model: str,
    utility_provider: Any | None,
    utility_model: str | None,
) -> dict[str, Any] | None:
    """Call LLM for experience-related tasks (compression, sufficiency, etc.)."""
    mode = (experience_mode or "utility").lower()
    if mode == "none":
        return None

    utility_ready = utility_provider is not None and bool(utility_model)
    use_utility = False
    if mode == "main":
        use_utility = False
    elif mode == "utility":
        if not utility_ready:
            logger.debug(
                "experience_model='utility' but utility_model not configured, falling back to main"
            )
        use_utility = utility_ready
    else:
        use_utility = utility_ready

    source = "main" if mode == "main" else "utility"
    if use_utility and utility_provider is not None and utility_model is not None:
        chosen_provider, chosen_model = utility_provider, utility_model
    else:
        chosen_provider, chosen_model = provider, model

    response = await chosen_provider.chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        model=chosen_model,
        temperature=0.3,
        max_tokens=512,
        source=source,
    )
    return parse_llm_json(response.content)


# ---------------------------------------------------------------------------
# 3. compress_state — trajectory compression with conditional self-audit
# ---------------------------------------------------------------------------


ExperienceLLMFn = Callable[[str, str], Awaitable[dict[str, Any] | None]]


async def compress_state(
    tool_trace: list[str],
    reasoning_snippets: list[str],
    failed_directions: list[str],
    previous_state: str | None = None,
    *,
    experience_mode: str | None,
    llm_fn: ExperienceLLMFn,
    label: str = "agent",
) -> str | None:
    """Compress execution trajectory into a structured state summary."""
    if experience_mode == "none":
        parts = [f"[Progress] {len(tool_trace)} steps completed"]
        if failed_directions:
            parts.append(f"[Failed] {'; '.join(failed_directions[-3:])}")
        recent = "; ".join(t.split("\u2192")[0].strip() for t in tool_trace[-5:])
        parts.append(f"[Recent] {recent}")
        return "\n".join(parts)

    trace_str = "\n".join(tool_trace[-10:])
    reasoning_str = " | ".join(reasoning_snippets[-5:]) if reasoning_snippets else "none"
    failed_str = "; ".join(failed_directions[-5:]) if failed_directions else "none"
    prev_section = (
        f"\n## Previous State (update this, don't start from scratch)\n{previous_state}"
        if previous_state
        else ""
    )
    has_failures = len(failed_directions) >= 2
    key_count = "4" if has_failures else "3"
    audit_section = ""
    if has_failures:
        audit_section = (
            '\n4. "audit": 1-2 actionable corrections \u2014 what specific mistake to avoid'
            " and what concrete action to take instead (NOT vague self-criticism)."
            " Omit if no clear correction exists."
        )
    prompt = (
        f"Compress this {label} execution state into a structured summary."
        f" Return JSON with exactly {key_count} keys:\n\n"
        '1. "conclusions": What has been established so far \u2014 key findings, partial answers, verified facts (2-3 sentences)\n'
        '2. "evidence": Sources consulted, tools used successfully, data gathered (1-2 sentences)\n'
        '3. "unexplored": Branches mentioned but NOT yet executed, open questions, alternative approaches to try next'
        f" (1-3 bullet points as a single string){audit_section}\n\n"
        f"## Execution Trace\n{trace_str}\n\n"
        f"## Reasoning Steps\n{reasoning_str[:400]}\n\n"
        f"## Failed Approaches\n{failed_str}{prev_section}\n\n"
        "Respond with ONLY valid JSON."
    )
    try:
        result = await llm_fn(
            "You are a trajectory compression agent. Respond only with valid JSON.",
            prompt,
        )
        if not result:
            return None
        parts = []
        if c := result.get("conclusions"):
            parts.append(f"[Conclusions] {c}")
        if e := result.get("evidence"):
            parts.append(f"[Evidence] {e}")
        if u := result.get("unexplored"):
            parts.append(f"[Unexplored branches \u2014 prioritize these next] {u}")
        if a := result.get("audit"):
            parts.append(f"[Audit \u2014 correct these mistakes] {a}")
        return "\n".join(parts) if parts else None
    except Exception as exc:
        logger.debug("{} state compression skipped: {}", label.capitalize(), exc)
        return None


# ---------------------------------------------------------------------------
# 4. check_sufficiency — auto-detect when enough info is gathered
# ---------------------------------------------------------------------------


async def check_sufficiency(
    user_request: str,
    tool_trace: list[str],
    *,
    experience_mode: str | None,
    llm_fn: ExperienceLLMFn,
) -> bool:
    """Check if enough information has been gathered to answer the request."""
    if experience_mode == "none":
        return False

    trace_summary = "; ".join(t.split("\u2192")[0].strip() for t in tool_trace[-8:])
    prompt = (
        "Given the user's request and the tools already executed,"
        " is there enough information to provide a complete answer?\n\n"
        f"User request: {user_request[:300]}\n"
        f"Steps taken: {trace_summary}\n\n"
        'Return JSON: {"sufficient": true} or {"sufficient": false}'
    )
    try:
        result = await llm_fn(
            "You are a task completion verifier. Respond only with valid JSON.",
            prompt,
        )
        return bool(result and result.get("sufficient"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 5. compact_messages — Layer 2 context compaction
# ---------------------------------------------------------------------------


def compact_messages(
    messages: list[dict[str, Any]],
    initial_messages: list[dict[str, Any]],
    last_state_text: str | None,
    artifact_store: "ArtifactStore | None",
    *,
    keep_blocks: int,
    label: str = "",
) -> list[dict[str, Any]]:
    """Layer 2: keep recent N tool-call blocks, archive the rest."""
    if artifact_store is not None:
        archive_key = f"{label}_compacted_context" if label else "compacted_context"
        try:
            artifact_store.archive_json("evicted_messages", archive_key, messages)
        except Exception as exc:
            logger.debug("{}ctx[L2] archive failed: {}", f"{label} " if label else "", exc)
    tool_blocks: list[list[dict[str, Any]]] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            tc_ids = {tc["id"] for tc in msg["tool_calls"]}
            block, j = [msg], i + 1
            while (
                j < len(messages)
                and messages[j].get("role") == "tool"
                and messages[j].get("tool_call_id") in tc_ids
            ):
                block.append(messages[j])
                j += 1
            tool_blocks.append(block)
            i = j
        else:
            i += 1
    recent_blocks = tool_blocks[-keep_blocks:]
    recent_msgs = [m for block in recent_blocks for m in block]
    state_note = (
        f"\n\n[Compacted context. Previous state:\n{last_state_text}\n]"
        if last_state_text
        else "\n\n[Compacted context: older messages archived.]"
    )
    system_msgs = [m for m in initial_messages if m.get("role") == "system"]
    dialogue_msgs = [
        m
        for m in messages
        if m.get("role") in {"user", "assistant"}
        and not (m.get("role") == "assistant" and m.get("tool_calls"))
    ]
    keep_dialogue = max(4, keep_blocks * 2)
    kept_dialogue = dialogue_msgs[-keep_dialogue:]
    kept_dialogue_ids = {id(m) for m in kept_dialogue}
    recent_msg_ids = {id(m) for m in recent_msgs}
    timeline_msgs = [m for m in messages if id(m) in kept_dialogue_ids or id(m) in recent_msg_ids]
    if timeline_msgs:
        for idx in range(len(timeline_msgs) - 1, -1, -1):
            item = timeline_msgs[idx]
            if item.get("role") != "user":
                continue
            original_content = str(item.get("content", ""))
            if "[Compacted context" not in original_content:
                timeline_msgs[idx] = {**item, "content": original_content + state_note}
            break
    new_messages = system_msgs + timeline_msgs
    log_prefix = f"{label} " if label else ""
    logger.debug(
        "{}ctx[L2] compacted: {} -> {} msgs, {} blocks",
        log_prefix,
        len(messages),
        len(new_messages),
        len(recent_blocks),
    )
    return new_messages
