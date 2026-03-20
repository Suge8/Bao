from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bao.agent._loop_agent_support_mixin import LoopAgentSupportMixin
from bao.agent._loop_user_message_models import ProcessDirectRequest

pytestmark = pytest.mark.unit


class _DummyAgent(LoopAgentSupportMixin):
    def __init__(self) -> None:
        self._connect_mcp = AsyncMock()
        self._process_message = AsyncMock(return_value=SimpleNamespace(content="ok"))


@pytest.mark.asyncio
async def test_process_direct_routes_through_wake_request_contract() -> None:
    agent = _DummyAgent()

    result = await agent.process_direct(
        ProcessDirectRequest(
            content="hello",
            channel=" Desktop ",
            chat_id=" local ",
            profile_id=" work ",
            reply_target_id=7,
            metadata={"source": "direct"},
            ephemeral=True,
        )
    )

    assert result == "ok"
    agent._connect_mcp.assert_awaited_once()
    msg, options = agent._process_message.await_args.args
    assert msg.channel == "desktop"
    assert msg.chat_id == "local"
    assert msg.metadata == {"source": "direct", "_ephemeral": True}
    assert options.session_key == "desktop:local"


def test_process_direct_request_keeps_default_hub_route_when_unchanged() -> None:
    request = ProcessDirectRequest(content="hello")

    route = request.to_route_key()

    assert route.session_key == "hub:direct"
    assert route.channel == "hub"
    assert route.chat_id == "direct"
