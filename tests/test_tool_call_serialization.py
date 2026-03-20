from __future__ import annotations

from types import SimpleNamespace

from bao.providers.base import ToolCallRequest, build_tool_call_request, normalize_tool_calls


def test_tool_call_request_serializes_openai_shape() -> None:
    tool_call = ToolCallRequest(
        id="call_1",
        name="search_web",
        arguments={"query": "bao"},
        provider_specific_fields={"foo": "bar"},
        function_provider_specific_fields={"strict": True},
    )

    payload = tool_call.to_openai_tool_call()

    assert payload["id"] == "call_1"
    assert payload["type"] == "function"
    assert payload["function"]["name"] == "search_web"
    assert payload["function"]["arguments"] == '{"query": "bao"}'
    assert payload["provider_specific_fields"] == {"foo": "bar"}
    assert payload["function"]["provider_specific_fields"] == {"strict": True}


def test_tool_call_request_preserves_raw_arguments_when_present() -> None:
    tool_call = ToolCallRequest(
        id="call_1",
        name="search_web",
        arguments={},
        raw_arguments='{"query"',
        argument_parse_error="parse failed",
    )

    payload = tool_call.to_openai_tool_call()

    assert payload["function"]["arguments"] == '{"query"'


def test_tool_call_request_serializes_normalized_arguments_after_successful_repair() -> None:
    tool_call = ToolCallRequest(
        id="call_1",
        name="search_web",
        arguments={"query": "bao"},
        raw_arguments='{"query":"bao",}',
        argument_parse_error=None,
    )

    payload = tool_call.to_openai_tool_call()

    assert payload["function"]["arguments"] == '{"query": "bao"}'


def test_normalize_tool_calls_records_argument_parse_error() -> None:
    message = SimpleNamespace(
        tool_calls=[
            SimpleNamespace(
                id="call_1",
                function=SimpleNamespace(name="search_web", arguments='{"query"'),
            )
        ]
    )

    tool_calls = normalize_tool_calls(message)

    assert len(tool_calls) == 1
    assert tool_calls[0].arguments == {}
    assert tool_calls[0].raw_arguments == '{"query"'
    assert tool_calls[0].argument_parse_error


def test_normalize_tool_calls_rejects_non_object_arguments() -> None:
    message = SimpleNamespace(
        function_call=SimpleNamespace(name="search_web", arguments='["bao"]')
    )

    tool_calls = normalize_tool_calls(message)

    assert len(tool_calls) == 1
    assert tool_calls[0].arguments == {}
    assert tool_calls[0].argument_parse_error == "tool arguments must decode to a JSON object"


def test_build_tool_call_request_records_non_dict_arguments() -> None:
    tool_call = build_tool_call_request("call_2", "search_web", '["bao"]')

    assert tool_call.arguments == {}
    assert tool_call.raw_arguments == '["bao"]'
    assert tool_call.argument_parse_error == "tool arguments must decode to a JSON object"
