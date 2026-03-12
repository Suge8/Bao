from __future__ import annotations

from bao.providers.base import ToolCallRequest


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
