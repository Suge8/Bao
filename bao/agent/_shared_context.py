"""Context compaction and tool-result patching helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from bao.agent.artifacts import ArtifactStore


@dataclass(frozen=True)
class DanglingToolResultRequest:
    tool_call: Any
    existing_tool_ids: set[str]
    inserted_ids: set[str]
    placeholder_content: str


@dataclass(frozen=True)
class CompactMessagesRequest:
    messages: list[dict[str, Any]]
    initial_messages: list[dict[str, Any]]
    last_state_text: str | None
    artifact_store: "ArtifactStore | None"
    keep_blocks: int
    label: str = ""


def patch_dangling_tool_results(
    messages: list[dict[str, Any]],
    *,
    placeholder_content: str = "[Tool call was interrupted and did not return a result.]",
) -> int:
    if not messages:
        return 0
    existing_tool_ids = {
        str(message.get("tool_call_id")).strip()
        for message in messages
        if message.get("role") == "tool" and isinstance(message.get("tool_call_id"), str)
    }
    existing_tool_ids.discard("")
    patched: list[dict[str, Any]] = []
    inserted_ids: set[str] = set()
    inserted_count = 0
    for message in messages:
        patched.append(message)
        if message.get("role") != "assistant":
            continue
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            continue
        for tool_call in tool_calls:
            inserted = _dangling_tool_result(
                DanglingToolResultRequest(
                    tool_call=tool_call,
                    existing_tool_ids=existing_tool_ids,
                    inserted_ids=inserted_ids,
                    placeholder_content=placeholder_content,
                )
            )
            if inserted is None:
                continue
            patched.append(inserted)
            existing_tool_ids.add(inserted["tool_call_id"])
            inserted_ids.add(inserted["tool_call_id"])
            inserted_count += 1
    if inserted_count:
        messages[:] = patched
    return inserted_count


def _dangling_tool_result(request: DanglingToolResultRequest) -> dict[str, Any] | None:
    tool_call = request.tool_call
    if not isinstance(tool_call, dict):
        return None
    raw_id = tool_call.get("id")
    if not isinstance(raw_id, str):
        return None
    tool_call_id = raw_id.strip()
    if (
        not tool_call_id
        or tool_call_id in request.existing_tool_ids
        or tool_call_id in request.inserted_ids
    ):
        return None
    tool_name = "unknown"
    function_payload = tool_call.get("function")
    if isinstance(function_payload, dict) and isinstance(function_payload.get("name"), str) and function_payload.get("name", "").strip():
        tool_name = function_payload["name"].strip()
    elif isinstance(tool_call.get("name"), str) and tool_call.get("name", "").strip():
        tool_name = tool_call["name"].strip()
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": request.placeholder_content,
    }


def compact_messages(request: CompactMessagesRequest) -> list[dict[str, Any]]:
    if request.artifact_store is not None:
        _archive_compacted_context(request.artifact_store, request.messages, request.label)
    recent_msgs = _recent_tool_block_messages(request.messages, request.keep_blocks)
    state_note = _state_note(request.last_state_text)
    system_msgs = [message for message in request.initial_messages if message.get("role") == "system"]
    dialogue_msgs = [
        message
        for message in request.messages
        if message.get("role") in {"user", "assistant"} and not (message.get("role") == "assistant" and message.get("tool_calls"))
    ]
    kept_dialogue = dialogue_msgs[-max(4, request.keep_blocks * 2) :]
    timeline_msgs = _timeline_messages(request.messages, kept_dialogue, recent_msgs)
    timeline_msgs = _append_state_note(timeline_msgs, state_note)
    new_messages = system_msgs + timeline_msgs
    log_prefix = f"{request.label} " if request.label else ""
    logger.debug(
        "{}ctx[L2] compacted: {} -> {} msgs, {} blocks",
        log_prefix,
        len(request.messages),
        len(new_messages),
        len(_recent_tool_blocks(request.messages, request.keep_blocks)),
    )
    return new_messages


def _archive_compacted_context(artifact_store: "ArtifactStore", messages: list[dict[str, Any]], label: str) -> None:
    archive_key = f"{label}_compacted_context" if label else "compacted_context"
    try:
        artifact_store.archive_json("evicted_messages", archive_key, messages)
    except Exception as exc:
        logger.debug("{}ctx[L2] archive failed: {}", f"{label} " if label else "", exc)


def _recent_tool_blocks(messages: list[dict[str, Any]], keep_blocks: int) -> list[list[dict[str, Any]]]:
    tool_blocks: list[list[dict[str, Any]]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.get("role") == "assistant" and message.get("tool_calls"):
            tool_call_ids = {tool_call["id"] for tool_call in message["tool_calls"]}
            block, index = _tool_block(messages, index, tool_call_ids)
            tool_blocks.append(block)
            continue
        index += 1
    return tool_blocks[-keep_blocks:]


def _tool_block(
    messages: list[dict[str, Any]],
    start_index: int,
    tool_call_ids: set[str],
) -> tuple[list[dict[str, Any]], int]:
    block = [messages[start_index]]
    index = start_index + 1
    while index < len(messages) and messages[index].get("role") == "tool" and messages[index].get("tool_call_id") in tool_call_ids:
        block.append(messages[index])
        index += 1
    return block, index


def _recent_tool_block_messages(messages: list[dict[str, Any]], keep_blocks: int) -> list[dict[str, Any]]:
    return [message for block in _recent_tool_blocks(messages, keep_blocks) for message in block]


def _state_note(last_state_text: str | None) -> str:
    if last_state_text:
        return f"\n\n[Compacted context. Previous state:\n{last_state_text}\n]"
    return "\n\n[Compacted context: older messages archived.]"


def _timeline_messages(
    messages: list[dict[str, Any]],
    kept_dialogue: list[dict[str, Any]],
    recent_msgs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    kept_dialogue_ids = {id(message) for message in kept_dialogue}
    recent_msg_ids = {id(message) for message in recent_msgs}
    return [message for message in messages if id(message) in kept_dialogue_ids or id(message) in recent_msg_ids]


def _append_state_note(timeline_msgs: list[dict[str, Any]], state_note: str) -> list[dict[str, Any]]:
    if not timeline_msgs:
        return [{"role": "user", "content": state_note.strip()}]
    for index in range(len(timeline_msgs) - 1, -1, -1):
        item = timeline_msgs[index]
        if item.get("role") != "user":
            continue
        original_content = str(item.get("content", ""))
        if "[Compacted context" in original_content:
            base = original_content.split("\n\n[Compacted context", 1)[0].rstrip()
            refreshed = (base + state_note) if base else state_note.strip()
            timeline_msgs[index] = {**item, "content": refreshed}
            return timeline_msgs
        if original_content.lstrip().startswith("[State after "):
            continue
        timeline_msgs[index] = {**item, "content": original_content + state_note}
        return timeline_msgs
    timeline_msgs.append({"role": "user", "content": state_note.strip()})
    return timeline_msgs
