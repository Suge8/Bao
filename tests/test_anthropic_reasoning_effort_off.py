from __future__ import annotations

import types

import pytest


class _FakeStream:
    def __init__(self, *, captured: dict[str, object]):
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __aiter__(self):
        async def _gen():
            if False:
                yield ""

        return _gen()

    async def get_final_message(self):
        usage = types.SimpleNamespace(input_tokens=1, output_tokens=1)
        return types.SimpleNamespace(content=[], usage=usage, stop_reason="end_turn")


class _FakeMessages:
    def __init__(self, *, captured: dict[str, object]):
        self._captured = captured

    def stream(self, **kwargs):
        self._captured.update(kwargs)
        return _FakeStream(captured=self._captured)


class _FakeAnthropicClient:
    def __init__(self, *, captured: dict[str, object]):
        self.messages = _FakeMessages(captured=captured)


@pytest.mark.asyncio
async def test_reasoning_effort_off_disables_thinking() -> None:
    from bao.providers.anthropic_provider import AnthropicProvider

    captured: dict[str, object] = {}
    provider = AnthropicProvider(api_key="dummy")
    provider._client = _FakeAnthropicClient(captured=captured)  # type: ignore[attr-defined]

    resp = await provider.chat(
        messages=[{"role": "user", "content": "ping"}],
        model="anthropic/claude-sonnet-4-20250514",
        max_tokens=8,
        temperature=0,
        reasoning_effort="off",
    )

    assert resp.finish_reason == "stop"
    assert "thinking" not in captured


def test_anthropic_provider_defers_client_construction() -> None:
    from bao.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider(api_key="dummy")

    assert provider._client is None


@pytest.mark.asyncio
async def test_reasoning_effort_low_enables_thinking_budget() -> None:
    from bao.providers.anthropic_provider import AnthropicProvider

    captured: dict[str, object] = {}
    provider = AnthropicProvider(api_key="dummy")
    provider._client = _FakeAnthropicClient(captured=captured)  # type: ignore[attr-defined]

    await provider.chat(
        messages=[{"role": "user", "content": "ping"}],
        model="anthropic/claude-sonnet-4-20250514",
        max_tokens=8,
        temperature=0,
        reasoning_effort="low",
    )

    assert captured.get("thinking") == {"type": "adaptive", "budget_tokens": 2048}
