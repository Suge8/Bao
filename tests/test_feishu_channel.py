from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bao.bus.queue import MessageBus
from bao.channels.feishu import FeishuChannel
from bao.config.schema import FeishuConfig


def _build_event(
    *,
    msg_type: str = "text",
    content: str = '{"text": "hello"}',
    chat_type: str = "group",
    mentions=None,
):
    return SimpleNamespace(
        event=SimpleNamespace(
            message=SimpleNamespace(
                message_id="m1",
                chat_id="oc_group",
                chat_type=chat_type,
                message_type=msg_type,
                content=content,
                mentions=mentions or [],
            ),
            sender=SimpleNamespace(
                sender_type="user",
                sender_id=SimpleNamespace(open_id="ou_user"),
            ),
        )
    )


def test_feishu_group_policy_defaults_to_mention() -> None:
    assert FeishuConfig().group_policy == "mention"


def test_feishu_is_bot_mentioned_accepts_empty_and_none_user_id() -> None:
    channel = FeishuChannel(FeishuConfig(group_policy="mention"), MessageBus())
    message = SimpleNamespace(
        content='{"text":"@bot hi"}',
        mentions=[
            SimpleNamespace(id=SimpleNamespace(user_id="", open_id="ou_bot")),
            SimpleNamespace(id=SimpleNamespace(user_id=None, open_id="ou_bot2")),
        ],
    )

    assert channel._is_bot_mentioned(message) is True


@pytest.mark.asyncio
async def test_feishu_group_policy_blocks_unmentioned_group_message() -> None:
    channel = FeishuChannel(
        FeishuConfig(group_policy="mention", react_emoji="THUMBSUP"),
        MessageBus(),
    )
    channel._running = True
    channel._add_reaction = AsyncMock()
    channel._handle_message = AsyncMock()

    await channel._on_message(_build_event())

    channel._handle_message.assert_not_awaited()
    channel._add_reaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_feishu_group_policy_allows_mentioned_group_message() -> None:
    channel = FeishuChannel(
        FeishuConfig(group_policy="mention", react_emoji="THUMBSUP"),
        MessageBus(),
    )
    channel._running = True
    channel._add_reaction = AsyncMock()
    channel._handle_message = AsyncMock()
    mentions = [SimpleNamespace(id=SimpleNamespace(user_id=None, open_id="ou_bot"))]

    await channel._on_message(_build_event(mentions=mentions))

    channel._handle_message.assert_awaited_once()
    channel._add_reaction.assert_awaited_once()


@pytest.mark.asyncio
async def test_feishu_download_audio_always_uses_opus_extension(monkeypatch, tmp_path) -> None:
    channel = FeishuChannel(FeishuConfig(), MessageBus())
    channel._client = object()
    monkeypatch.setattr("bao.channels.feishu.get_media_path", lambda: tmp_path)
    channel._download_file_sync = MagicMock(return_value=(b"abc", "clip"))

    file_path, content = await channel._download_and_save_media("audio", {"file_key": "file123"})

    assert file_path is not None
    assert file_path.endswith(".opus")
    assert content == "[audio: clip.opus]"


@pytest.mark.asyncio
async def test_feishu_on_message_handles_media_msg_type() -> None:
    channel = FeishuChannel(FeishuConfig(group_policy="open"), MessageBus())
    channel._running = True
    channel._add_reaction = AsyncMock()
    channel._handle_message = AsyncMock()
    channel._download_and_save_media = AsyncMock(return_value=("/tmp/video.mp4", "[media: video.mp4]"))

    await channel._on_message(
        _build_event(msg_type="media", content='{"file_key": "file123"}', chat_type="p2p")
    )

    kwargs = channel._handle_message.await_args.kwargs
    assert kwargs["media"] == ["/tmp/video.mp4"]
    assert kwargs["content"] == "[media: video.mp4]"


def test_feishu_run_ws_client_blocking_uses_dedicated_loop(monkeypatch) -> None:
    import lark_oapi.ws.client as ws_client_module

    channel = FeishuChannel(FeishuConfig(), MessageBus())
    seen: list[asyncio.AbstractEventLoop] = []

    class _FakeWSClient:
        def start(self) -> None:
            seen.append(asyncio.get_event_loop())
            seen.append(ws_client_module.loop)

    main_loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(main_loop)
        channel._ws_client = _FakeWSClient()
        monkeypatch.setattr(ws_client_module, "loop", None, raising=False)

        channel._run_ws_client_blocking()
    finally:
        asyncio.set_event_loop(None)
        main_loop.close()

    assert len(seen) == 2
    assert seen[0] is seen[1]
    assert seen[0].is_closed()
