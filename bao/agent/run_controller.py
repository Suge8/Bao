from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from bao.agent.artifacts import ArtifactStore


@dataclass
class RunLoopState:
    iteration: int = 0
    final_content: str | None = None
    provider_error: bool = False
    interrupted: bool = False
    consecutive_errors: int = 0
    total_errors: int = 0
    total_tool_steps_for_sufficiency: int = 0
    next_sufficiency_at: int = 8
    force_final_response: bool = False
    force_final_backoff_used: bool = False
    last_state_attempt_at: int = 0
    last_state_text: str | None = None


@dataclass
class PreIterationCheckRequest:
    messages: list[dict[str, Any]]
    initial_messages: list[dict[str, Any]]
    user_request: str
    artifact_store: ArtifactStore | None
    state: RunLoopState
    tool_trace: list[str]
    reasoning_snippets: list[str]
    failed_directions: list[str]
    sufficiency_trace: list[str]
    ctx_mgmt: str
    compact_bytes: int
    compress_state: Callable[[list[str], list[str], list[str], str | None], Awaitable[str | None]]
    check_sufficiency: Callable[[str, list[str], str | None], Awaitable[bool]]
    compact_messages: Callable[..., list[dict[str, Any]]]
    is_interrupted: Callable[[], bool] | None = None


async def apply_pre_iteration_checks(request: PreIterationCheckRequest) -> list[dict[str, Any]]:
    state = request.state
    messages = request.messages
    if request.is_interrupted is not None and request.is_interrupted():
        state.interrupted = True
        return messages

    tool_steps = len(request.tool_trace)
    steps_since_attempt = tool_steps - state.last_state_attempt_at
    if tool_steps >= 5 and steps_since_attempt >= 5:
        compressed_state = await request.compress_state(
            request.tool_trace,
            request.reasoning_snippets,
            request.failed_directions,
            state.last_state_text,
        )
        state.last_state_attempt_at = tool_steps
        if compressed_state:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"[State after {tool_steps} steps]\n{compressed_state}\n\n"
                        "Use this state freely — adopt useful parts, ignore irrelevant "
                        "ones, and prioritize unexplored branches."
                    ),
                }
            )
            state.last_state_text = compressed_state
            request.tool_trace.clear()
            request.reasoning_snippets.clear()
            request.failed_directions.clear()
            state.consecutive_errors = 0
            state.last_state_attempt_at = 0

    if state.total_tool_steps_for_sufficiency >= state.next_sufficiency_at:
        if await request.check_sufficiency(
            request.user_request,
            request.sufficiency_trace,
            state.last_state_text,
        ):
            messages.append(
                {
                    "role": "user",
                    "content": "You now have sufficient information. Provide your final answer.",
                }
            )
            state.force_final_response = True
        while state.next_sufficiency_at <= state.total_tool_steps_for_sufficiency:
            state.next_sufficiency_at += 4

    return _maybe_compact_messages(request, messages)


def _maybe_compact_messages(
    request: PreIterationCheckRequest,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if request.ctx_mgmt not in ("auto", "aggressive"):
        return messages
    try:
        approx_bytes = len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))
    except Exception:
        approx_bytes = 0
    if approx_bytes < request.compact_bytes:
        return messages
    return request.compact_messages(
        messages=messages,
        initial_messages=request.initial_messages,
        last_state_text=request.state.last_state_text,
        artifact_store=request.artifact_store,
    )


def build_error_feedback(consecutive_errors: int, failed_directions: list[str]) -> str | None:
    if consecutive_errors >= 3:
        return (
            "Multiple tool errors occurred. STOP retrying the same approach.\n"
            f"Failed directions so far: {'; '.join(failed_directions[-5:])}\n"
            "Try a completely different strategy."
        )
    if consecutive_errors > 0:
        failed_hint = (
            f"\nAlready tried and failed: {'; '.join(failed_directions[-3:])}"
            if len(failed_directions) > 1
            else ""
        )
        return (
            "The tool returned an error. Analyze what went wrong and try a different "
            f"approach.{failed_hint}"
        )
    return None
