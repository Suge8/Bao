"""Shared utilities for AgentLoop and SubagentManager.

Extracted to eliminate duplication between loop.py and subagent.py.
Both classes retain thin wrapper methods that delegate here.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, TypedDict

import json_repair
from loguru import logger

if TYPE_CHECKING:
    from bao.agent.artifacts import ArtifactStore

from bao.agent.protocol import ToolErrorCategory, ToolErrorInfo

SubagentResultStatus = Literal["ok", "error"]
SUBAGENT_RESULT_EVENT_TYPE = "subagent_result"


class SubagentResultEvent(TypedDict):
    type: Literal["subagent_result"]
    task_id: str
    label: str
    task: str
    status: SubagentResultStatus
    result: str


def _normalize_subagent_result_status(status: Any) -> SubagentResultStatus:
    return "error" if status == "error" else "ok"


def build_subagent_result_event(
    *,
    task_id: str,
    label: str,
    task: str,
    status: Any,
    result: str,
) -> SubagentResultEvent:
    return {
        "type": SUBAGENT_RESULT_EVENT_TYPE,
        "task_id": task_id.strip(),
        "label": label.strip(),
        "task": task.strip(),
        "status": _normalize_subagent_result_status(status),
        "result": result.strip(),
    }


def parse_subagent_result_event(metadata: dict[str, Any] | None) -> SubagentResultEvent | None:
    if not isinstance(metadata, dict):
        return None
    raw_event = metadata.get("system_event")
    if not isinstance(raw_event, dict):
        return None
    if raw_event.get("type") != SUBAGENT_RESULT_EVENT_TYPE:
        return None
    task = raw_event.get("task")
    if not isinstance(task, str) or not task.strip():
        return None
    result = raw_event.get("result")
    label = raw_event.get("label")
    task_id = raw_event.get("task_id")
    return build_subagent_result_event(
        task_id=task_id if isinstance(task_id, str) else "",
        label=label if isinstance(label, str) else "",
        task=task,
        status=raw_event.get("status"),
        result=result if isinstance(result, str) else "",
    )


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


# Mirrors loop.py:_TOOL_CANCELLED_MSG — kept in sync manually.
_TOOL_CANCELLED_MSG = "Cancelled by soft interrupt."


def parse_tool_error(
    tool_name: str,
    result: str,
    error_keywords: tuple[str, ...],
) -> ToolErrorInfo | None:
    """Classify a tool result into a structured :class:`ToolErrorInfo`.

    Returns ``None`` when the result does not look like an error at all.
    Returns ``ToolErrorInfo(is_error=False, ...)`` for non-error special
    cases such as soft-interrupt cancellation.
    """
    result_text = (result or "").strip()
    if not result_text:
        return None

    result_lower = result_text.lower()
    result_normalized = result_lower.lstrip()
    excerpt = sanitize_trace_text(result_text, 200)

    def _info(
        *,
        is_error: bool = True,
        category: str,
        code: str | None = None,
        retryable: bool = True,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> ToolErrorInfo:
        return ToolErrorInfo(
            is_error=is_error,
            tool_name=tool_name,
            category=category,
            code=code,
            retryable=retryable,
            message=message or category,
            raw_excerpt=excerpt,
            details=details or {},
        )

    # ── 1. interrupted (soft-interrupt cancellation) ──────────────────
    if result_text == _TOOL_CANCELLED_MSG:
        return _info(
            is_error=False,
            category=ToolErrorCategory.INTERRUPTED,
            code="soft_interrupt",
            retryable=False,
            message="Cancelled by soft interrupt",
        )

    # ── 2. invalid_params ───────────────────────────────────────────
    if result_normalized.startswith("error: invalid parameters for tool"):
        return _info(
            category=ToolErrorCategory.INVALID_PARAMS,
            code="invalid_params",
            message="Invalid tool parameters",
        )

    # ── 3. tool_not_found ──────────────────────────────────────────
    if result_normalized.startswith("error: tool '") and "not found" in result_normalized:
        return _info(
            category=ToolErrorCategory.TOOL_NOT_FOUND,
            code="tool_not_found",
            retryable=False,
            message="Tool not found",
        )

    # ── 4. execution_error prefix ──────────────────────────────────
    if result_normalized.startswith("error executing"):
        return _info(
            category=ToolErrorCategory.EXECUTION_ERROR,
            code="execution_error",
            message="Error executing tool",
        )

    # ── 5. web_search special ──────────────────────────────────────
    if tool_name == "web_search":
        if result_normalized.startswith("error:"):
            return _info(
                category=ToolErrorCategory.EXECUTION_ERROR,
                code="web_search_error",
                message="Web search error",
            )
        return None

    # ── 6. web_fetch special ───────────────────────────────────────
    if tool_name == "web_fetch":
        if result_normalized.startswith("error:"):
            return _info(
                category=ToolErrorCategory.EXECUTION_ERROR,
                code="web_fetch_error",
                message="Web fetch error",
            )
        if result_normalized.startswith("{"):
            try:
                payload = json.loads(result_normalized)
            except json.JSONDecodeError:
                payload = None
                if re.match(r'^\{\s*"error"\s*:', result_normalized):
                    return _info(
                        category=ToolErrorCategory.EXECUTION_ERROR,
                        code="web_fetch_error",
                        message="Web fetch JSON error (malformed)",
                    )
            if isinstance(payload, dict) and payload.get("error"):
                return _info(
                    category=ToolErrorCategory.EXECUTION_ERROR,
                    code="web_fetch_error",
                    message="Web fetch JSON error",
                )
        return None

    # ── 7. exec special ────────────────────────────────────────────
    if tool_name == "exec":
        exit_match = re.search(r"exit\s*code\s*:\s*(-?\d+)", result_normalized)
        if exit_match:
            try:
                exit_code = int(exit_match.group(1))
                if exit_code != 0:
                    return _info(
                        category=ToolErrorCategory.EXECUTION_ERROR,
                        code="exec_exit_code",
                        message=f"Exit code {exit_code}",
                        details={"exit_code": exit_code},
                    )
            except ValueError:
                pass
        if any(kw in result_lower for kw in error_keywords):
            return _info(
                category=ToolErrorCategory.UNKNOWN,
                code="keyword_match",
                message="Error keyword detected",
            )
        return None

    # ── 8. coding_agent / coding_agent_details ──────────────────────
    if tool_name in {"coding_agent", "coding_agent_details"}:
        payload = None
        if result_normalized.startswith("{"):
            try:
                payload = json.loads(result_normalized)
            except json.JSONDecodeError:
                payload = None
        if payload is None and "{" in result_normalized and "}" in result_normalized:
            start = result_normalized.find("{")
            end = result_normalized.rfind("}") + 1
            if 0 <= start < end:
                try:
                    payload = json.loads(result_normalized[start:end])
                except json.JSONDecodeError:
                    payload = None
        if isinstance(payload, dict):
            status = payload.get("status")
            if isinstance(status, str) and status.lower() in {"error", "failed"}:
                return _info(
                    category=ToolErrorCategory.EXECUTION_ERROR,
                    code="coding_agent_status",
                    message=f"Coding agent status: {status}",
                )
            if payload.get("error"):
                return _info(
                    category=ToolErrorCategory.EXECUTION_ERROR,
                    code="coding_agent_error",
                    message="Coding agent error field set",
                )
            for key in ("exit_code", "exitcode", "exitCode", "returncode", "return_code"):
                code_val = payload.get(key)
                if isinstance(code_val, int) and code_val != 0:
                    return _info(
                        category=ToolErrorCategory.EXECUTION_ERROR,
                        code="coding_agent_exit_code",
                        message=f"Coding agent exit code {code_val}",
                        details={"exit_code": code_val},
                    )
            for key in ("timed_out", "timedout", "timedOut"):
                tv = payload.get(key)
                if isinstance(tv, bool) and tv:
                    return _info(
                        category=ToolErrorCategory.TIMEOUT,
                        code="coding_agent_timeout",
                        retryable=True,
                        message="Coding agent timed out",
                    )
        if any(kw in result_lower for kw in error_keywords):
            return _info(
                category=ToolErrorCategory.UNKNOWN,
                code="keyword_match",
                message="Error keyword detected",
            )
        return None

    # ── 9. fallback: keyword-only ───────────────────────────────────
    if any(kw in result_lower for kw in error_keywords):
        return _info(
            category=ToolErrorCategory.UNKNOWN,
            code="keyword_match",
            message="Error keyword detected",
        )
    return None


def has_tool_error(tool_name: str, result: str, error_keywords: tuple[str, ...]) -> bool:
    """Return True if *result* indicates a tool failure."""
    info = parse_tool_error(tool_name, result, error_keywords)
    return bool(info and info.is_error)


def sanitize_visible_text(text: str) -> str:
    return text.replace("\n", " ").replace("\r", "").replace("|", "/")


def sanitize_trace_text(text: Any, max_len: int) -> str:
    normalized = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    compact = " ".join(normalized.split())
    return compact[:max_len]


def summarize_tool_args_for_trace(
    tool_name: str,
    args: dict[str, Any] | None,
    *,
    max_len: int = 60,
) -> str:
    payload = args or {}
    if tool_name in {"write_file", "edit_file"}:
        path = payload.get("path")
        return sanitize_trace_text(path if isinstance(path, str) else "<redacted>", max_len)
    if tool_name == "exec":
        command = payload.get("command")
        if isinstance(command, str):
            return f"<redacted:{len(command)} chars>"

    first_arg = next(iter(payload.values()), "") if payload else ""
    return sanitize_trace_text(first_arg, max_len)


def build_tool_trace_entry(
    trace_idx: int,
    tool_name: str,
    args_preview: str,
    has_error: bool,
    result: Any,
    *,
    result_max_len: int = 100,
) -> str:
    safe_args = sanitize_trace_text(args_preview, 60)
    safe_result = sanitize_trace_text(result, result_max_len)
    return (
        f"T{trace_idx} {tool_name}({safe_args}) → {'ERROR' if has_error else 'ok'}: {safe_result}"
    )


def push_failed_direction(
    failed_directions: list[str],
    entry: str,
    *,
    max_items: int = 20,
) -> None:
    if failed_directions and failed_directions[-1] == entry:
        return
    failed_directions.append(entry)
    if len(failed_directions) > max_items:
        del failed_directions[:-max_items]


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


def _validate_state(
    result: dict[str, Any],
    tool_trace: list[str],
    failed_directions: list[str],
) -> dict[str, Any]:
    """Validate compressed state; fill missing fields with rule-based fallback."""
    if not result.get("conclusions"):
        recent = "; ".join(t.split("\u2192")[0].strip() for t in tool_trace[-5:])
        result["conclusions"] = (
            f"{len(tool_trace)} steps completed. Recent: {recent}"
            if recent
            else f"{len(tool_trace)} steps completed."
        )
    if not result.get("evidence"):
        ok_steps = [t for t in tool_trace if "\u2192 ok" in t]
        result["evidence"] = (
            "; ".join(s.split("\u2192")[0].strip() for s in ok_steps[-3:])
            or "no successful steps yet"
        )
    if not result.get("unexplored"):
        if failed_directions:
            result["unexplored"] = (
                f"Retry with different approach: {'; '.join(failed_directions[-2:])}"
            )
        else:
            result["unexplored"] = (
                "Review last 3 tool steps, verify remaining requirements, then answer."
            )
    return result


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
        '2. "evidence": Reference specific trace steps by T# number (e.g. "T1 confirmed X, T3 revealed Y"). Sources consulted, data gathered (1-2 sentences)\n'
        '3. "unexplored": Actionable next steps as imperative commands (e.g. "Run search for X", "Read file Y to check Z").'
        f" Each item must be a concrete action, not a vague description (1-3 bullet points as a single string){audit_section}\n\n"
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
        # Wave 3: validate + rule-based fallback for missing fields
        result = _validate_state(result, tool_trace, failed_directions)
        parts = []
        if c := result.get("conclusions"):
            parts.append(f"[Conclusions] {sanitize_trace_text(c, 500)}")
        if e := result.get("evidence"):
            parts.append(f"[Evidence] {sanitize_trace_text(e, 500)}")
        if u := result.get("unexplored"):
            parts.append(
                f"[Unexplored branches \u2014 prioritize these next] {sanitize_trace_text(u, 500)}"
            )
        if a := result.get("audit"):
            parts.append(f"[Audit \u2014 correct these mistakes] {sanitize_trace_text(a, 500)}")
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
    last_state_text: str | None = None,
) -> bool:
    """Check if enough information has been gathered to answer the request."""
    if experience_mode == "none":
        return False

    trace_summary = "; ".join(t.split("\u2192")[0].strip() for t in tool_trace[-8:])
    open_items = ""
    conclusions = ""
    evidence = ""
    if last_state_text:
        for line in last_state_text.splitlines():
            line_text = line.strip()
            if not open_items and line_text.startswith("[Unexplored"):
                open_items = line_text
            elif not conclusions and line_text.startswith("[Conclusions]"):
                conclusions = line_text
            elif not evidence and line_text.startswith("[Evidence]"):
                evidence = line_text
    open_section = f"\nOpen items from last state: {open_items}\n" if open_items else ""
    state_section = ""
    if conclusions or evidence:
        pieces = []
        if conclusions:
            pieces.append(f"State conclusions: {conclusions}")
        if evidence:
            pieces.append(f"State evidence: {evidence}")
        state_section = "\n" + "\n".join(pieces) + "\n"
    prompt = (
        "Given the user's request and the tools already executed,"
        " is there enough information to provide a complete answer?\n\n"
        f"User request: {user_request[:300]}\n"
        f"Steps taken: {trace_summary}\n"
        f"{state_section}"
        f"{open_section}\n"
        "Open items may be stale if already addressed in recent steps.\n"
        "If there are open items that are critical to the request, answer false.\n"
        'Return JSON: {"sufficient": true} or {"sufficient": false}'
    )
    try:
        result = await llm_fn(
            "You are a task completion verifier. Respond only with valid JSON.",
            prompt,
        )
        value = result.get("sufficient") if result else None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
        return False
    except Exception:
        return False


def patch_dangling_tool_results(
    messages: list[dict[str, Any]],
    *,
    placeholder_content: str = "[Tool call was interrupted and did not return a result.]",
) -> int:
    if not messages:
        return 0

    existing_tool_ids = {
        str(m.get("tool_call_id")).strip()
        for m in messages
        if m.get("role") == "tool" and isinstance(m.get("tool_call_id"), str)
    }
    existing_tool_ids.discard("")

    patched: list[dict[str, Any]] = []
    inserted_ids: set[str] = set()
    inserted_count = 0

    for msg in messages:
        patched.append(msg)
        if msg.get("role") != "assistant":
            continue

        tool_calls = msg.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            continue

        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue

            raw_id = tc.get("id")
            if not isinstance(raw_id, str):
                continue
            tool_call_id = raw_id.strip()
            if not tool_call_id:
                continue
            if tool_call_id in existing_tool_ids or tool_call_id in inserted_ids:
                continue

            tool_name = "unknown"
            fn = tc.get("function")
            if (
                isinstance(fn, dict)
                and isinstance(fn.get("name"), str)
                and fn.get("name", "").strip()
            ):
                tool_name = fn["name"].strip()
            elif isinstance(tc.get("name"), str) and tc.get("name", "").strip():
                tool_name = tc["name"].strip()

            patched.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "content": placeholder_content,
                }
            )
            existing_tool_ids.add(tool_call_id)
            inserted_ids.add(tool_call_id)
            inserted_count += 1

    if inserted_count:
        messages[:] = patched

    return inserted_count


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
        appended = False
        for idx in range(len(timeline_msgs) - 1, -1, -1):
            item = timeline_msgs[idx]
            if item.get("role") != "user":
                continue
            original_content = str(item.get("content", ""))
            if "[Compacted context" in original_content:
                base = original_content.split("\n\n[Compacted context", 1)[0].rstrip()
                refreshed = (base + state_note) if base else state_note.strip()
                timeline_msgs[idx] = {**item, "content": refreshed}
                appended = True
                break
            if original_content.lstrip().startswith("[State after "):
                continue
            timeline_msgs[idx] = {**item, "content": original_content + state_note}
            appended = True
            break
        if not appended:
            timeline_msgs.append({"role": "user", "content": state_note.strip()})
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
