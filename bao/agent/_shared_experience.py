"""Experience, compression, and sufficiency helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from loguru import logger

from bao.providers.base import ChatRequest

from ._shared_common import parse_llm_json
from ._shared_trace import sanitize_trace_text

ExperienceLLMFn = Callable[[str, str], Awaitable[dict[str, Any] | None]]


@dataclass(frozen=True)
class ExperienceLLMRequest:
    system: str
    prompt: str
    experience_mode: str | None
    provider: Any
    model: str
    utility_provider: Any | None = None
    utility_model: str | None = None
    service_tier: str | None = None


@dataclass(frozen=True)
class CompressStateRequest:
    tool_trace: list[str]
    reasoning_snippets: list[str]
    failed_directions: list[str]
    experience_mode: str | None
    llm_fn: ExperienceLLMFn
    previous_state: str | None = None
    label: str = "agent"


@dataclass(frozen=True)
class CompressStatePromptRequest:
    label: str
    tool_trace: list[str]
    reasoning_snippets: list[str]
    failed_directions: list[str]
    previous_state: str | None = None


@dataclass(frozen=True)
class SufficiencyRequest:
    user_request: str
    tool_trace: list[str]
    experience_mode: str | None
    llm_fn: ExperienceLLMFn
    last_state_text: str | None = None


async def call_experience_llm(request: ExperienceLLMRequest) -> dict[str, Any] | None:
    mode = (request.experience_mode or "utility").lower()
    if mode == "none":
        return None
    use_utility = _use_utility_model(mode, request.utility_provider, request.utility_model)
    source = "main" if mode == "main" else "utility"
    chosen_provider, chosen_model = (
        (request.utility_provider, request.utility_model)
        if use_utility
        else (request.provider, request.model)
    )
    response = await chosen_provider.chat(
        ChatRequest(
            messages=[
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
            model=chosen_model,
            temperature=0.3,
            max_tokens=512,
            service_tier=request.service_tier,
            source=source,
        )
    )
    return parse_llm_json(response.content)


def _use_utility_model(mode: str, utility_provider: Any | None, utility_model: str | None) -> bool:
    utility_ready = utility_provider is not None and bool(utility_model)
    if mode == "main":
        return False
    if mode == "utility" and not utility_ready:
        logger.debug("experience_model='utility' but utility_model not configured, falling back to main")
    return utility_ready


def _validate_state(
    result: dict[str, Any],
    tool_trace: list[str],
    failed_directions: list[str],
) -> dict[str, Any]:
    if not result.get("conclusions"):
        recent = "; ".join(t.split("→")[0].strip() for t in tool_trace[-5:])
        result["conclusions"] = f"{len(tool_trace)} steps completed. Recent: {recent}" if recent else f"{len(tool_trace)} steps completed."
    if not result.get("evidence"):
        ok_steps = [trace for trace in tool_trace if "→ ok" in trace]
        result["evidence"] = "; ".join(step.split("→")[0].strip() for step in ok_steps[-3:]) or "no successful steps yet"
    if not result.get("unexplored"):
        result["unexplored"] = (
            f"Retry with different approach: {'; '.join(failed_directions[-2:])}"
            if failed_directions
            else "Review last 3 tool steps, verify remaining requirements, then answer."
        )
    return result


async def compress_state(request: CompressStateRequest) -> str | None:
    if request.experience_mode == "none":
        return _fallback_progress_state(request.tool_trace, request.failed_directions)
    prompt = _compress_state_prompt(
        CompressStatePromptRequest(
            label=request.label,
            tool_trace=request.tool_trace,
            reasoning_snippets=request.reasoning_snippets,
            failed_directions=request.failed_directions,
            previous_state=request.previous_state,
        )
    )
    try:
        result = await request.llm_fn(
            "You are a trajectory compression agent. Respond only with valid JSON.",
            prompt,
        )
    except Exception as exc:
        logger.debug("{} state compression skipped: {}", request.label.capitalize(), exc)
        return None
    if not result:
        return None
    return _format_compressed_state(
        _validate_state(result, request.tool_trace, request.failed_directions)
    )


def _fallback_progress_state(tool_trace: list[str], failed_directions: list[str]) -> str:
    parts = [f"[Progress] {len(tool_trace)} steps completed"]
    if failed_directions:
        parts.append(f"[Failed] {'; '.join(failed_directions[-3:])}")
    recent = "; ".join(trace.split("→")[0].strip() for trace in tool_trace[-5:])
    parts.append(f"[Recent] {recent}")
    return "\n".join(parts)


def _compress_state_prompt(request: CompressStatePromptRequest) -> str:
    trace_str = "\n".join(request.tool_trace[-10:])
    reasoning_str = " | ".join(request.reasoning_snippets[-5:]) if request.reasoning_snippets else "none"
    failed_str = "; ".join(request.failed_directions[-5:]) if request.failed_directions else "none"
    prev_section = (
        f"\n## Previous State (update this, don't start from scratch)\n{request.previous_state}"
        if request.previous_state
        else ""
    )
    has_failures = len(request.failed_directions) >= 2
    key_count = "4" if has_failures else "3"
    audit_section = ""
    if has_failures:
        audit_section = (
            '\n4. "audit": 1-2 actionable corrections — what specific mistake to avoid'
            " and what concrete action to take instead (NOT vague self-criticism)."
            " Omit if no clear correction exists."
    )
    return (
        f"Compress this {request.label} execution state into a structured summary. Return JSON with exactly {key_count} keys:\n\n"
        '1. "conclusions": What has been established so far — key findings, partial answers, verified facts (2-3 sentences)\n'
        '2. "evidence": Reference specific trace steps by T# number (e.g. "T1 confirmed X, T3 revealed Y"). Sources consulted, data gathered (1-2 sentences)\n'
        '3. "unexplored": Actionable next steps as imperative commands (e.g. "Run search for X", "Read file Y to check Z"). Each item must be a concrete action, not a vague description (1-3 bullet points as a single string)'
        f"{audit_section}\n\n## Execution Trace\n{trace_str}\n\n## Reasoning Steps\n{reasoning_str[:400]}\n\n## Failed Approaches\n{failed_str}{prev_section}\n\nRespond with ONLY valid JSON."
    )


def _format_compressed_state(result: dict[str, Any]) -> str | None:
    parts = []
    if conclusions := result.get("conclusions"):
        parts.append(f"[Conclusions] {sanitize_trace_text(conclusions, 500)}")
    if evidence := result.get("evidence"):
        parts.append(f"[Evidence] {sanitize_trace_text(evidence, 500)}")
    if unexplored := result.get("unexplored"):
        parts.append(f"[Unexplored branches — prioritize these next] {sanitize_trace_text(unexplored, 500)}")
    if audit := result.get("audit"):
        parts.append(f"[Audit — correct these mistakes] {sanitize_trace_text(audit, 500)}")
    return "\n".join(parts) if parts else None


async def check_sufficiency(request: SufficiencyRequest) -> bool:
    if request.experience_mode == "none":
        return False
    prompt = _sufficiency_prompt(
        request.user_request,
        request.tool_trace,
        request.last_state_text,
    )
    try:
        result = await request.llm_fn(
            "You are a task completion verifier. Respond only with valid JSON.",
            prompt,
        )
    except Exception:
        return False
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


def _sufficiency_prompt(user_request: str, tool_trace: list[str], last_state_text: str | None) -> str:
    trace_summary = "; ".join(trace.split("→")[0].strip() for trace in tool_trace[-8:])
    open_items, conclusions, evidence = _state_prompt_parts(last_state_text)
    open_section = f"\nOpen items from last state: {open_items}\n" if open_items else ""
    state_section = ""
    if conclusions or evidence:
        pieces = []
        if conclusions:
            pieces.append(f"State conclusions: {conclusions}")
        if evidence:
            pieces.append(f"State evidence: {evidence}")
        state_section = "\n" + "\n".join(pieces) + "\n"
    return (
        "Given the user's request and the tools already executed, is there enough information to provide a complete answer?\n\n"
        f"User request: {user_request[:300]}\n"
        f"Steps taken: {trace_summary}\n"
        f"{state_section}{open_section}\n"
        "Open items may be stale if already addressed in recent steps.\n"
        "If there are open items that are critical to the request, answer false.\n"
        'Return JSON: {"sufficient": true} or {"sufficient": false}'
    )


def _state_prompt_parts(last_state_text: str | None) -> tuple[str, str, str]:
    open_items = ""
    conclusions = ""
    evidence = ""
    if not last_state_text:
        return open_items, conclusions, evidence
    for line in last_state_text.splitlines():
        line_text = line.strip()
        if not open_items and line_text.startswith("[Unexplored"):
            open_items = line_text
        elif not conclusions and line_text.startswith("[Conclusions]"):
            conclusions = line_text
        elif not evidence and line_text.startswith("[Evidence]"):
            evidence = line_text
    return open_items, conclusions, evidence
