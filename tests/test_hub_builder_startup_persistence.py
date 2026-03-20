"""Startup greeting persistence tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bao.hub.builder import send_startup_greeting
from tests._hub_builder_testkit import make_hub_config, set_channels, startup_options

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_startup_greeting_ready_stage_does_not_persist_external_message() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()
    fake_agent.model = "right-gpt/gpt-5.3-codex"
    fake_agent.max_tokens = 4096
    fake_agent.temperature = 0.1
    fake_agent.provider = MagicMock()
    fake_agent.provider.chat = AsyncMock(return_value=MagicMock(content="hello"))

    session_manager = MagicMock()

    class FakeRuntimeChannels:
        async def wait_started(self) -> None:
            return None

        async def wait_ready(self, _name: str) -> None:
            return None

        async def send_outbound(self, _msg) -> None:
            return None

    config = make_hub_config()
    set_channels(config, feishu=["ou_123"])

    with patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"):
        await send_startup_greeting(
            fake_agent,
            fake_bus,
            startup_options(
                config,
                channels=FakeRuntimeChannels(),
                session_manager=session_manager,
            ),
        )

    fake_bus.publish_outbound.assert_not_awaited()
    session_manager.get_or_create.assert_not_called()
    session_manager.save.assert_not_called()
    session_manager.mark_desktop_seen_ai_if_active.assert_not_called()


@pytest.mark.asyncio
async def test_startup_onboarding_persists_external_message_to_session_manager() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()

    class StubSession:
        def __init__(self, key: str) -> None:
            self.key = key
            self.messages: list[dict[str, object]] = []

        def add_message(self, role: str, content: str, **kwargs: object) -> None:
            self.messages.append({"role": role, "content": content, **kwargs})

    session = StubSession("imessage:13800138000")
    session_manager = MagicMock()
    session_manager.get_or_create.return_value = session
    session_manager.resolve_active_session_key.return_value = "imessage:13800138000"

    class FakeRuntimeChannels:
        async def wait_started(self) -> None:
            return None

        async def wait_ready(self, _name: str) -> None:
            return None

        async def send_outbound(self, _msg) -> None:
            return None

    config = make_hub_config()
    set_channels(config, imessage=["13800138000"])

    with (
        patch("bao.hub._builder_startup.asyncio.sleep", new=AsyncMock()),
        patch("bao.config.onboarding.detect_onboarding_stage", return_value="lang_select"),
        patch("bao.config.onboarding.LANG_PICKER", "picker"),
    ):
        await send_startup_greeting(
            MagicMock(),
            fake_bus,
            startup_options(
                config,
                channels=FakeRuntimeChannels(),
                session_manager=session_manager,
            ),
        )

    fake_bus.publish_outbound.assert_not_awaited()
    session_manager.get_or_create.assert_called_once_with("imessage:13800138000")
    session_manager.save.assert_called_once_with(session)
    session_manager.mark_desktop_seen_ai_if_active.assert_called_once_with("imessage:13800138000")
    assert session.messages == [
        {
            "role": "assistant",
            "content": "picker",
            "status": "done",
            "format": "markdown",
            "entrance_style": "assistantReceived",
        }
    ]


@pytest.mark.asyncio
async def test_startup_greeting_does_not_persist_external_message_when_send_fails() -> None:
    fake_bus = MagicMock()
    fake_bus.publish_outbound = AsyncMock()
    fake_agent = MagicMock()
    fake_agent.model = "right-gpt/gpt-5.3-codex"
    fake_agent.provider = MagicMock()
    fake_agent.provider.chat = AsyncMock(return_value=MagicMock(content="hello"))

    class FakeRuntimeChannels:
        async def wait_started(self) -> None:
            return None

        async def wait_ready(self, _name: str) -> None:
            return None

        async def send_outbound(self, _msg) -> None:
            raise RuntimeError("send denied")

    session_manager = MagicMock()
    config = make_hub_config()
    set_channels(config, feishu=["ou_123"])

    with patch("bao.config.onboarding.detect_onboarding_stage", return_value="ready"):
        await send_startup_greeting(
            fake_agent,
            fake_bus,
            startup_options(
                config,
                channels=FakeRuntimeChannels(),
                session_manager=session_manager,
            ),
        )

    fake_bus.publish_outbound.assert_not_awaited()
    session_manager.get_or_create.assert_not_called()
    session_manager.save.assert_not_called()
