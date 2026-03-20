from __future__ import annotations

from loguru import logger

from bao.agent.artifacts_models import (
    ToolOutputBudgetEvent,
    ToolOutputBudgetRequest,
    WriteArtifactFileRequest,
)
from bao.agent.tool_result import (
    ToolTextResult,
    cleanup_result_file,
    make_file_preview,
    make_preview,
    read_head_chars,
)


def apply_tool_output_budget(request: ToolOutputBudgetRequest) -> tuple[str, ToolOutputBudgetEvent]:
    if isinstance(request.result, ToolTextResult):
        return _apply_file_result_budget(request)
    return _apply_text_result_budget(request)


def _apply_file_result_budget(request: ToolOutputBudgetRequest) -> tuple[str, ToolOutputBudgetEvent]:
    event = ToolOutputBudgetEvent()
    result = request.result
    assert isinstance(result, ToolTextResult)
    try:
        if _should_offload(request, result.chars):
            pointer = _offload_file_result(request, result)
            if pointer is not None:
                event.offloaded = True
                event.offloaded_chars = result.chars
                return pointer, event
        if result.chars <= request.hard_chars:
            return result.path.read_text(encoding="utf-8", errors="replace"), event
        clipped, omitted = _clip_file_result(request, result)
        event.hard_clipped = True
        event.hard_clipped_chars = omitted
        return clipped, event
    finally:
        cleanup_result_file(result)


def _offload_file_result(
    request: ToolOutputBudgetRequest,
    result: ToolTextResult,
) -> str | None:
    if request.store is None:
        return None
    try:
        preview = make_file_preview(result.path, request.preview_chars)
        ref = request.store.write_text_file(
            WriteArtifactFileRequest(
                kind="tool_output",
                name_hint=f"{request.tool_name}_{request.tool_call_id}",
                source_path=result.path,
                size=result.chars,
                move_source=result.cleanup,
            )
        )
        return request.store.format_pointer(ref, preview)
    except Exception as exc:
        logger.debug("ctx[L1] offload failed for {}: {}", request.tool_name, exc)
        return None


def _clip_file_result(
    request: ToolOutputBudgetRequest,
    result: ToolTextResult,
) -> tuple[str, int]:
    preview = read_head_chars(result.path, request.hard_chars)
    omitted = max(0, result.chars - len(preview))
    clipped = preview + (
        "\n... "
        f"(hard-truncated {omitted} chars for context safety from tool '{request.tool_name}'; "
        "request details explicitly if needed)"
    )
    return clipped, omitted


def _apply_text_result_budget(request: ToolOutputBudgetRequest) -> tuple[str, ToolOutputBudgetEvent]:
    event = ToolOutputBudgetEvent()
    original_text = str(request.result)
    processed = original_text
    if _should_offload(request, len(original_text)):
        offloaded = _offload_text_result(request, original_text)
        if offloaded is not None:
            processed = offloaded
            event.offloaded = True
            event.offloaded_chars = len(original_text)
    processed, omitted = _hard_clip_tool_result(
        processed,
        tool_name=request.tool_name,
        hard_chars=request.hard_chars,
    )
    if omitted > 0:
        event.hard_clipped = True
        event.hard_clipped_chars = omitted
    return processed, event


def _offload_text_result(request: ToolOutputBudgetRequest, processed: str) -> str | None:
    if request.store is None:
        return None
    try:
        preview = make_preview(processed, request.preview_chars)
        ref = request.store.write_text(
            "tool_output",
            f"{request.tool_name}_{request.tool_call_id}",
            processed,
        )
        return request.store.format_pointer(ref, preview)
    except Exception as exc:
        logger.debug("ctx[L1] offload failed for {}: {}", request.tool_name, exc)
        return None


def _should_offload(request: ToolOutputBudgetRequest, size: int) -> bool:
    return (
        request.store is not None
        and request.ctx_mgmt in ("auto", "aggressive")
        and size >= request.offload_chars
    )


def _hard_clip_tool_result(result: str, tool_name: str, hard_chars: int = 6000) -> tuple[str, int]:
    limit = max(500, int(hard_chars))
    if len(result) <= limit:
        return result, 0
    omitted = len(result) - limit
    clipped = result[:limit]
    suffix = (
        "\n... "
        f"(hard-truncated {omitted} chars for context safety from tool '{tool_name}'; "
        "request details explicitly if needed)"
    )
    return clipped + suffix, omitted
