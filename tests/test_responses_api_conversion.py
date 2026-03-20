"""Conversion and ID-normalization tests for Responses API."""

from bao.providers.responses_compat import (
    _normalize_call_id,
    append_responses_tool_call_arguments,
    build_internal_tool_call_id,
    build_responses_tool_call_request,
    convert_messages_to_responses,
    convert_tools_to_responses,
    parse_responses_json,
    replace_responses_tool_call_arguments,
    sanitize_responses_input_items,
    start_responses_tool_call,
)


def test_convert_messages_to_responses():
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "function": {"name": "search", "arguments": '{"q": "test"}'}}
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "result"},
    ]
    system_prompt, input_items = convert_messages_to_responses(messages)
    assert system_prompt == "You are helpful.", f"Got: {system_prompt}"
    assert len(input_items) == 4, f"Expected 4 items, got {len(input_items)}"
    assert input_items[0]["role"] == "user"
    assert input_items[1]["type"] == "message"
    assert input_items[1]["role"] == "assistant"
    assert input_items[2]["type"] == "function_call"
    assert input_items[2]["name"] == "search"
    assert input_items[3]["type"] == "function_call_output"
    assert input_items[3]["output"] == "result"
    print("✓ convert_messages_to_responses")


def test_convert_messages_to_responses_accepts_system_blocks() -> None:
    messages = [
        {
            "role": "system",
            "content": [
                {"type": "text", "text": "You are helpful."},
            ],
        },
        {"role": "user", "content": "Hello"},
    ]
    system_prompt, input_items = convert_messages_to_responses(messages)
    assert system_prompt == "You are helpful."
    assert len(input_items) == 1
    assert input_items[0]["role"] == "user"


def test_convert_tools_to_responses():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search",
                "parameters": {"type": "object"},
            },
        }
    ]
    result = convert_tools_to_responses(tools)
    assert len(result) == 1
    assert result[0]["type"] == "function"
    assert result[0]["name"] == "search"
    assert "parameters" in result[0]
    print("✓ convert_tools_to_responses")


def test_parse_responses_json():
    data = {
        "status": "completed",
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "Hello!"}]},
            {
                "type": "function_call",
                "call_id": "c1",
                "id": "fc1",
                "name": "tool",
                "arguments": '{"x": 1}',
            },
        ],
        "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
    }
    content, tool_calls, finish_reason, usage = parse_responses_json(data)
    assert content == "Hello!", f"Got: {content}"
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "tool"
    assert tool_calls[0].arguments == {"x": 1}
    assert finish_reason == "stop"
    assert usage["prompt_tokens"] == 10
    assert usage["completion_tokens"] == 20
    print("✓ parse_responses_json")


def test_convert_messages_to_responses_normalizes_long_call_id() -> None:
    raw_call_id = "call_" + ("x" * 90)
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": f"{raw_call_id}|fc_1", "function": {"name": "search", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": f"{raw_call_id}|fc_1", "content": "result"},
    ]

    _, input_items = convert_messages_to_responses(messages)

    assert input_items[0]["type"] == "function_call"
    assert input_items[1]["type"] == "function_call_output"
    assert input_items[0]["call_id"] == input_items[1]["call_id"]
    assert len(input_items[0]["call_id"]) <= 64


def test_sanitize_responses_input_items_normalizes_composite_call_id() -> None:
    raw_call_id = "call_" + ("q" * 90)
    input_items = [
        {
            "type": "function_call",
            "id": "fc_1",
            "call_id": f"{raw_call_id}|fc_1",
            "name": "search",
            "arguments": "{}",
        },
        {
            "type": "function_call_output",
            "call_id": f"{raw_call_id}|fc_1",
            "output": "ok",
        },
    ]

    sanitized = sanitize_responses_input_items(input_items)

    assert sanitized[0]["call_id"] == sanitized[1]["call_id"]
    assert len(sanitized[0]["call_id"]) <= 64


def test_normalize_call_id_keeps_short_id() -> None:
    assert _normalize_call_id("call_123") == "call_123"


def test_normalize_call_id_shortens_long_id_stably() -> None:
    raw_call_id = "call_" + ("y" * 120)
    first = _normalize_call_id(raw_call_id)
    second = _normalize_call_id(raw_call_id)

    assert first == second
    assert len(first) <= 64


def test_build_internal_tool_call_id_normalizes_call_id() -> None:
    raw_call_id = "call_" + ("z" * 100)
    internal_id = build_internal_tool_call_id(raw_call_id, "fc_1")

    call_id, item_id = internal_id.split("|", 1)
    assert item_id == "fc_1"
    assert len(call_id) <= 64


def test_parse_responses_json_normalizes_internal_tool_call_id() -> None:
    raw_call_id = "call_" + ("q" * 90)
    data = {
        "status": "completed",
        "output": [
            {
                "type": "function_call",
                "call_id": raw_call_id,
                "id": "fc_long",
                "name": "tool",
                "arguments": "{}",
            }
        ],
    }

    _, tool_calls, _, _ = parse_responses_json(data)

    assert len(tool_calls) == 1
    call_id, item_id = tool_calls[0].id.split("|", 1)
    assert item_id == "fc_long"
    assert len(call_id) <= 64


def test_build_responses_tool_call_request_uses_shared_buffer_lifecycle() -> None:
    raw_call_id = "call_" + ("b" * 90)
    tool_call_buffers: dict[str, dict[str, object]] = {}
    item = {
        "type": "function_call",
        "call_id": raw_call_id,
        "id": "fc_2",
        "name": "search",
        "arguments": "{}",
    }

    start_responses_tool_call(tool_call_buffers, item)
    append_responses_tool_call_arguments(tool_call_buffers, raw_call_id, '{"q":')
    replace_responses_tool_call_arguments(tool_call_buffers, raw_call_id, '{"q":"ok"}')

    tool_call = build_responses_tool_call_request(item, tool_call_buffers)

    assert tool_call is not None
    assert tool_call.arguments == {"q": "ok"}
    call_id, item_id = tool_call.id.split("|", 1)
    assert item_id == "fc_2"
    assert len(call_id) <= 64


def test_build_responses_tool_call_request_coerces_non_object_arguments() -> None:
    item = {
        "type": "function_call",
        "call_id": "call_list_args",
        "id": "fc_list",
        "name": "search",
        "arguments": '["unexpected"]',
    }

    tool_call = build_responses_tool_call_request(item)

    assert tool_call is not None
    assert tool_call.arguments == {}
    assert tool_call.raw_arguments is None
    assert tool_call.argument_parse_error is None
