"""General shared helpers for loop/subagent coordination."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict

import json_repair
from loguru import logger

from bao.providers.base import ChatRequest

from ._shared_context import patch_dangling_tool_results

SubagentResultStatus = Literal["ok", "error"]
SUBAGENT_RESULT_EVENT_TYPE = "subagent_result"


class SubagentResultEvent(TypedDict):
    type: Literal["subagent_result"]
    task_id: str
    label: str
    task: str
    status: SubagentResultStatus
    result: str


@dataclass(frozen=True)
class SubagentResultEventRequest:
    task_id: str
    label: str
    task: str
    status: Any
    result: str


@dataclass(frozen=True)
class ScreenshotMarkerRequest:
    tool_name: str
    result: str | Any
    read_error_label: str
    unsafe_path_label: str


@dataclass(frozen=True)
class ProviderChatRequest:
    provider: Any
    request: ChatRequest
    patched_log_label: str


def _normalize_subagent_result_status(status: Any) -> SubagentResultStatus:
    return "error" if status == "error" else "ok"


def build_subagent_result_event(request: SubagentResultEventRequest) -> SubagentResultEvent:
    return {
        "type": SUBAGENT_RESULT_EVENT_TYPE,
        "task_id": request.task_id.strip(),
        "label": request.label.strip(),
        "task": request.task.strip(),
        "status": _normalize_subagent_result_status(request.status),
        "result": request.result.strip(),
    }


def parse_subagent_result_payload(raw_event: Any) -> SubagentResultEvent | None:
    if not isinstance(raw_event, dict) or raw_event.get("type") != SUBAGENT_RESULT_EVENT_TYPE:
        return None
    task = raw_event.get("task")
    if not isinstance(task, str) or not task.strip():
        return None
    result = raw_event.get("result")
    label = raw_event.get("label")
    task_id = raw_event.get("task_id")
    return build_subagent_result_event(
        SubagentResultEventRequest(
            task_id=task_id if isinstance(task_id, str) else "",
            label=label if isinstance(label, str) else "",
            task=task,
            status=raw_event.get("status"),
            result=result if isinstance(result, str) else "",
        )
    )


def parse_llm_json(content: str | None) -> dict[str, Any] | None:
    text = (content or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    result = json_repair.loads(text)
    return result if isinstance(result, dict) else None


def strip_think_tags(text: str | None) -> str | None:
    if not text:
        return None
    return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None


def handle_screenshot_marker(request: ScreenshotMarkerRequest) -> tuple[str | Any, str | None]:
    result = request.result
    if (
        request.tool_name != "screenshot"
        or not isinstance(result, str)
        or not result.startswith("__SCREENSHOT__:")
    ):
        return result, None
    image_base64: str | None = None
    screenshot_path = result[len("__SCREENSHOT__:") :].strip()
    result = "[screenshot unavailable]"
    screenshot_file = Path(screenshot_path).expanduser()
    tmp_dir = Path(tempfile.gettempdir()).resolve()
    safe_marker = _is_safe_screenshot_marker(screenshot_file, tmp_dir)
    if safe_marker:
        image_base64, result = _read_screenshot_marker(screenshot_file, request.read_error_label)
    else:
        logger.warning("⚠️ {}: {}", request.unsafe_path_label, screenshot_file)
    return result, image_base64


def _is_safe_screenshot_marker(screenshot_file: Path, tmp_dir: Path) -> bool:
    try:
        resolved_parent = screenshot_file.resolve(strict=False).parent
    except Exception:
        resolved_parent = None
    return screenshot_file.name.startswith("bao_screenshot_") and resolved_parent == tmp_dir


def _read_screenshot_marker(screenshot_file: Path, read_error_label: str) -> tuple[str | None, str]:
    image_base64: str | None = None
    result = "[screenshot unavailable]"
    try:
        import base64

        with screenshot_file.open("rb") as screenshot_stream:
            image_base64 = base64.b64encode(screenshot_stream.read()).decode()
        result = "[screenshot captured]"
    except Exception as screenshot_err:
        logger.warning("⚠️ {}: {}: {}", read_error_label, screenshot_file, screenshot_err)
    finally:
        try:
            if screenshot_file.exists():
                screenshot_file.unlink()
        except Exception:
            pass
    return image_base64, result


def maybe_backoff_empty_final(
    *,
    force_final_response: bool,
    force_final_backoff_used: bool,
    clean_final: str | None,
) -> tuple[bool, bool, dict[str, str] | None]:
    if not force_final_response or force_final_backoff_used or clean_final:
        return force_final_response, force_final_backoff_used, None
    return (
        False,
        True,
        {
            "role": "user",
            "content": (
                "Your previous final response was empty. "
                "If more evidence is needed, use tools briefly and then provide a "
                "complete final answer."
            ),
        },
    )


async def call_provider_chat(request: ProviderChatRequest) -> Any:
    repaired = patch_dangling_tool_results(request.request.messages)
    if repaired:
        logger.warning(
            "{} {} dangling tool_call(s) before provider chat",
            request.patched_log_label,
            repaired,
        )
    try:
        return await request.provider.chat(request.request)
    finally:
        for message in request.request.messages:
            message.pop("_image", None)
