"""Test message tool suppress logic for final replies."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.message import MessageTool
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMResponse, ToolCallRequest


class TestMessageToolSuppressLogic:
    """Test that final reply is only suppressed when message tool sends to same target."""

    @pytest.mark.asyncio
    async def test_final_reply_suppressed_when_message_tool_sends_to_same_target(
        self, tmp_path: Path
    ) -> None:
        """If message tool sends to the same (channel, chat_id), final reply is suppressed."""
        bus = MessageBus()
        provider = MagicMock()
        provider.get_default_model.return_value = "test-model"
        loop = AgentLoop(
            bus=bus, provider=provider, workspace=tmp_path, model="test-model", memory_window=10
        )

        # First call returns tool call, second call returns final response
        tool_call = ToolCallRequest(
            id="call1",
            name="message",
            arguments={"content": "Hello from tool", "channel": "feishu", "chat_id": "chat123"}
        )

        call_count = 0

        def mock_chat(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(content="", tool_calls=[tool_call])
            else:
                return LLMResponse(content="Done", tool_calls=[])

        loop.provider.chat = AsyncMock(side_effect=mock_chat)
        loop.tools.get_definitions = MagicMock(return_value=[])

        # Track outbound messages
        sent_messages: list[OutboundMessage] = []

        async def _capture_outbound(msg: OutboundMessage) -> None:
            sent_messages.append(msg)

        # Set up message tool with callback
        message_tool = loop.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_send_callback(_capture_outbound)

        msg = InboundMessage(
            channel="feishu", sender_id="user1", chat_id="chat123", content="Send a message"
        )
        result = await loop._process_message(msg)

        # Message tool should have sent to the same target
        assert len(sent_messages) == 1
        assert sent_messages[0].channel == "feishu"
        assert sent_messages[0].chat_id == "chat123"

        # Final reply should be None (suppressed)
        assert result is None

    @pytest.mark.asyncio
    async def test_final_reply_sent_when_message_tool_sends_to_different_target(
        self, tmp_path: Path
    ) -> None:
        """If message tool sends to a different target, final reply is still sent."""
        bus = MessageBus()
        provider = MagicMock()
        provider.get_default_model.return_value = "test-model"
        loop = AgentLoop(
            bus=bus, provider=provider, workspace=tmp_path, model="test-model", memory_window=10
        )

        # First call returns tool call to email, second call returns final response
        tool_call = ToolCallRequest(
            id="call1",
            name="message",
            arguments={"content": "Email content", "channel": "email", "chat_id": "user@example.com"}
        )

        call_count = 0

        def mock_chat(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(content="", tool_calls=[tool_call])
            else:
                return LLMResponse(content="I've sent the email.", tool_calls=[])

        loop.provider.chat = AsyncMock(side_effect=mock_chat)
        loop.tools.get_definitions = MagicMock(return_value=[])

        # Track outbound messages
        sent_messages: list[OutboundMessage] = []

        async def _capture_outbound(msg: OutboundMessage) -> None:
            sent_messages.append(msg)

        # Set up message tool with callback
        message_tool = loop.tools.get("message")
        if isinstance(message_tool, MessageTool):
            message_tool.set_send_callback(_capture_outbound)

        msg = InboundMessage(
            channel="feishu", sender_id="user1", chat_id="chat123", content="Send an email"
        )
        result = await loop._process_message(msg)

        # Message tool should have sent to email
        assert len(sent_messages) == 1
        assert sent_messages[0].channel == "email"
        assert sent_messages[0].chat_id == "user@example.com"

        # Final reply should be sent to Feishu (not suppressed)
        assert result is not None
        assert result.channel == "feishu"
        assert result.chat_id == "chat123"
        assert "email" in result.content.lower() or "sent" in result.content.lower()

    @pytest.mark.asyncio
    async def test_final_reply_sent_when_no_message_tool_used(self, tmp_path: Path) -> None:
        """If no message tool is used, final reply is always sent."""
        bus = MessageBus()
        provider = MagicMock()
        provider.get_default_model.return_value = "test-model"
        loop = AgentLoop(
            bus=bus, provider=provider, workspace=tmp_path, model="test-model", memory_window=10
        )

        # Mock provider to return a simple response without tool calls
        loop.provider.chat = AsyncMock(return_value=LLMResponse(
            content="Hello! How can I help you?",
            tool_calls=[]
        ))
        loop.tools.get_definitions = MagicMock(return_value=[])

        msg = InboundMessage(
            channel="feishu", sender_id="user1", chat_id="chat123", content="Hi"
        )
        result = await loop._process_message(msg)

        # Final reply should be sent
        assert result is not None
        assert result.channel == "feishu"
        assert result.chat_id == "chat123"
        assert "Hello" in result.content


class TestMessageToolTurnTracking:
    """Test MessageTool's turn tracking functionality."""

    def test_turn_sends_tracking(self) -> None:
        """MessageTool correctly tracks sends per turn."""
        tool = MessageTool()

        # Initially empty
        assert tool.get_turn_sends() == []

        # Simulate sends
        tool._turn_sends.append(("feishu", "chat1"))
        tool._turn_sends.append(("email", "user@example.com"))

        sends = tool.get_turn_sends()
        assert len(sends) == 2
        assert ("feishu", "chat1") in sends
        assert ("email", "user@example.com") in sends

    def test_start_turn_clears_tracking(self) -> None:
        """start_turn() clears the turn sends list."""
        tool = MessageTool()
        tool._turn_sends.append(("feishu", "chat1"))
        assert len(tool.get_turn_sends()) == 1

        tool.start_turn()
        assert tool.get_turn_sends() == []

    def test_get_turn_sends_returns_copy(self) -> None:
        """get_turn_sends() returns a copy, not the original list."""
        tool = MessageTool()
        tool._turn_sends.append(("feishu", "chat1"))

        sends = tool.get_turn_sends()
        sends.append(("email", "user@example.com"))  # Modify the copy

        # Original should be unchanged
        assert len(tool.get_turn_sends()) == 1
