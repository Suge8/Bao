from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bao.channels import imessage as imessage_module
from bao.channels.imessage import IMessageChannel
from bao.config.schema import IMessageConfig


def test_coalesce_message_rows_uses_rowid_as_single_fact_source() -> None:
    rows = [
        (11, "你在吗", "+8618127419003", "chat-a"),
        (11, "你在吗", "+8618127419003", "chat-a"),
        (12, "在干嘛", "+8618127419003", "chat-a"),
    ]

    assert imessage_module._coalesce_message_rows(rows) == [
        (11, "你在吗", "+8618127419003", "chat-a"),
        (12, "在干嘛", "+8618127419003", "chat-a"),
    ]


@pytest.mark.asyncio
async def test_imessage_poll_deduplicates_duplicate_rowids_before_dispatch() -> None:
    channel = IMessageChannel(IMessageConfig(enabled=True, allow_from=["+8618127419003"]), AsyncMock())
    channel._query_new = lambda: [
        (21, "你在吗", "+8618127419003", "chat-a"),
        (21, "你在吗", "+8618127419003", "chat-a"),
    ]
    channel._query_attachments = lambda _rowids: {}
    channel._handle_message = AsyncMock()

    await channel._poll()

    channel._handle_message.assert_awaited_once()
    inbound = channel._handle_message.await_args.args[0]
    assert inbound.content == "你在吗"
    assert inbound.chat_id == "chat-a"
