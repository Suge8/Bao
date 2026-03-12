from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels.feishu import FeishuChannel
from bao.config.schema import FeishuConfig


def test_split_elements_by_table_limit_keeps_one_table_per_group() -> None:
    groups = FeishuChannel._split_elements_by_table_limit(
        [
            {"tag": "markdown", "content": "intro"},
            {"tag": "table"},
            {"tag": "markdown", "content": "middle"},
            {"tag": "table"},
            {"tag": "markdown", "content": "tail"},
        ]
    )

    assert len(groups) == 2
    assert sum(1 for item in groups[0] if item.get("tag") == "table") == 1
    assert sum(1 for item in groups[1] if item.get("tag") == "table") == 1


@pytest.mark.asyncio
async def test_feishu_send_splits_multi_table_content_into_multiple_cards() -> None:
    channel = FeishuChannel(
        FeishuConfig(enabled=True, app_id="app", app_secret="secret"),
        MessageBus(),
    )
    channel._client = object()
    channel._send_interactive_elements = AsyncMock(return_value="om_1")

    content = (
        "| A |\n| - |\n| 1 |\n\n"
        "between\n\n"
        "| B |\n| - |\n| 2 |\n"
    )
    await channel.send(OutboundMessage(channel="feishu", chat_id="ou_1", content=content))

    assert channel._send_interactive_elements.await_count == 2


@pytest.mark.asyncio
async def test_feishu_send_keeps_single_card_when_only_one_table() -> None:
    channel = FeishuChannel(
        FeishuConfig(enabled=True, app_id="app", app_secret="secret"),
        MessageBus(),
    )
    channel._client = object()
    channel._send_interactive_elements = AsyncMock(return_value="om_1")

    await channel.send(
        OutboundMessage(
            channel="feishu",
            chat_id="ou_1",
            content="before\n\n| A |\n| - |\n| 1 |\n\nafter",
        )
    )

    channel._send_interactive_elements.assert_awaited_once()
