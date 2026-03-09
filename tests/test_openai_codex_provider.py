import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx

from bao.providers.openai_codex_provider import OpenAICodexProvider, _consume_sse


def test_codex_provider_does_not_retry_with_insecure_tls(monkeypatch) -> None:
    provider = OpenAICodexProvider(default_model="openai-codex/gpt-5.1-codex")
    attempts: list[bool] = []

    async def _fake_request_codex(
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
        verify: bool,
        on_progress=None,
    ) -> tuple[str, list[Any], str]:
        del url, headers, body, on_progress
        attempts.append(verify)
        raise RuntimeError("CERTIFICATE_VERIFY_FAILED")

    monkeypatch.setattr(
        "bao.providers.openai_codex_provider.get_codex_token",
        lambda: SimpleNamespace(account_id="acct_1", access="token"),
    )
    monkeypatch.setattr("bao.providers.openai_codex_provider._request_codex", _fake_request_codex)

    result = asyncio.run(provider.chat(messages=[{"role": "user", "content": "hi"}]))

    assert attempts == [True]
    assert result.finish_reason == "error"
    assert "CERTIFICATE_VERIFY_FAILED" in (result.content or "")


def test_codex_provider_normalizes_long_call_id_in_replayed_history(monkeypatch) -> None:
    provider = OpenAICodexProvider(default_model="openai-codex/gpt-5.1-codex")
    captured_body: dict[str, Any] = {}
    raw_call_id = "call_" + ("x" * 90)

    async def _fake_request_codex(
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
        verify: bool,
        on_progress=None,
    ) -> tuple[str, list[Any], str]:
        del url, headers, verify, on_progress
        captured_body.update(body)
        return "ok", [], "stop"

    monkeypatch.setattr(
        "bao.providers.openai_codex_provider.get_codex_token",
        lambda: SimpleNamespace(account_id="acct_1", access="token"),
    )
    monkeypatch.setattr("bao.providers.openai_codex_provider._request_codex", _fake_request_codex)

    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"{raw_call_id}|fc_1",
                    "function": {"name": "search", "arguments": json.dumps({"q": "test"})},
                }
            ],
        },
        {"role": "tool", "tool_call_id": f"{raw_call_id}|fc_1", "content": "result"},
    ]

    result = asyncio.run(provider.chat(messages=messages))

    assert result.finish_reason == "stop"
    input_items = captured_body["input"]
    assert input_items[0]["type"] == "function_call"
    assert input_items[1]["type"] == "function_call_output"
    assert input_items[0]["call_id"] == input_items[1]["call_id"]
    assert len(input_items[0]["call_id"]) <= 64


def test_codex_consume_sse_normalizes_internal_tool_call_id(monkeypatch) -> None:
    raw_call_id = "call_" + ("y" * 90)

    async def _fake_iter_sse(_response: Any):
        yield {
            "type": "response.output_item.added",
            "item": {
                "type": "function_call",
                "call_id": raw_call_id,
                "id": "fc_99",
                "name": "search",
                "arguments": "{}",
            },
        }
        yield {
            "type": "response.output_item.done",
            "item": {
                "type": "function_call",
                "call_id": raw_call_id,
                "id": "fc_99",
                "name": "search",
                "arguments": "{}",
            },
        }
        yield {"type": "response.completed", "response": {"status": "completed"}}

    monkeypatch.setattr("bao.providers.openai_codex_provider._iter_sse", _fake_iter_sse)

    _, tool_calls, finish_reason = asyncio.run(_consume_sse(response=httpx.Response(200)))

    assert finish_reason == "stop"
    assert len(tool_calls) == 1
    call_id, item_id = tool_calls[0].id.split("|", 1)
    assert item_id == "fc_99"
    assert len(call_id) <= 64
