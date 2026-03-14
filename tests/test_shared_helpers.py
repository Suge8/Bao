import asyncio
import base64
import tempfile
from pathlib import Path

from bao.agent import shared


def test_handle_screenshot_marker_reads_safe_temp_file_and_cleans_up(tmp_path: Path) -> None:
    screenshot_path = Path(tempfile.gettempdir()) / "bao_screenshot_test.png"
    screenshot_path.write_bytes(b"png-bytes")

    result, image_b64 = shared.handle_screenshot_marker(
        "screenshot",
        f"__SCREENSHOT__:{screenshot_path}",
        read_error_label="read failed",
        unsafe_path_label="unsafe path",
    )

    assert result == "[screenshot captured]"
    assert image_b64 == base64.b64encode(b"png-bytes").decode()
    assert not screenshot_path.exists()


def test_maybe_backoff_empty_final_returns_retry_prompt_once() -> None:
    force_final, backoff_used, retry_prompt = shared.maybe_backoff_empty_final(
        force_final_response=True,
        force_final_backoff_used=False,
        clean_final=None,
    )

    assert force_final is False
    assert backoff_used is True
    assert retry_prompt is not None
    assert retry_prompt["role"] == "user"

    second = shared.maybe_backoff_empty_final(
        force_final_response=force_final,
        force_final_backoff_used=backoff_used,
        clean_final=None,
    )
    assert second == (False, True, None)


def test_call_provider_chat_repairs_messages_and_clears_images() -> None:
    class DummyProvider:
        def __init__(self) -> None:
            self.calls = []

        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            return {"ok": True}

    provider = DummyProvider()
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "demo", "arguments": "{}"}}],
            "_image": "temp",
        }
    ]

    result = asyncio.run(
        shared.call_provider_chat(
            provider=provider,
            messages=messages,
            tools=[],
            model="test-model",
            temperature=0.1,
            max_tokens=16,
            reasoning_effort=None,
            service_tier="priority",
            source="test",
            patched_log_label="Patched",
        )
    )

    assert result == {"ok": True}
    assert provider.calls and provider.calls[0]["source"] == "test"
    assert provider.calls[0]["service_tier"] == "priority"
    assert "_image" not in messages[0]
    assert len(messages) == 2
    assert messages[1]["role"] == "tool"
