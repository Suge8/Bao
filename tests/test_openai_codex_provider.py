import asyncio
from types import SimpleNamespace
from typing import Any

from bao.providers.openai_codex_provider import OpenAICodexProvider


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
