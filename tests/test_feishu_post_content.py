import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest

from bao.bus.queue import MessageBus
from bao.channels.feishu import FeishuChannel, _extract_interactive_content, _extract_post_text
from bao.config.schema import FeishuConfig


def test_extract_post_text_supports_post_wrapper_shape() -> None:
    payload = {
        "post": {
            "zh_cn": {
                "title": "日报",
                "content": [[{"tag": "text", "text": "完成"}]],
            }
        }
    }

    text = _extract_post_text(payload)
    assert text == "日报 完成"


def test_extract_post_text_keeps_direct_shape_behavior() -> None:
    payload = {
        "title": "Daily",
        "content": [[{"tag": "text", "text": "report"}]],
    }

    text = _extract_post_text(payload)
    assert text == "Daily report"


def test_extract_interactive_content_supports_nested_elements_shape() -> None:
    payload = {
        "elements": [
            [
                {"tag": "markdown", "content": "hello"},
                {"tag": "div", "text": {"content": "world"}},
            ]
        ]
    }

    parts = _extract_interactive_content(payload)
    assert "hello" in parts
    assert "world" in parts


@pytest.mark.asyncio
async def test_feishu_stop_uses_async_to_thread_join(monkeypatch: pytest.MonkeyPatch) -> None:
    channel = FeishuChannel(FeishuConfig(), MessageBus())

    ws_thread = MagicMock(spec=threading.Thread)
    ws_thread.is_alive.return_value = True
    ws_client = MagicMock()
    channel._ws_thread = ws_thread
    channel._ws_client = ws_client
    channel._running = True

    async def _fake_to_thread(func, *args, **kwargs):
        func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", _fake_to_thread)

    await channel.stop()

    assert channel._ws_thread is None
    assert channel._ws_client is None
    assert channel._loop is None
    ws_client.stop.assert_called_once_with()
    ws_thread.join.assert_called_once_with(timeout=3)


def test_on_message_sync_ignores_events_after_stop() -> None:
    channel = FeishuChannel(FeishuConfig(), MessageBus())
    channel._running = False
    loop = MagicMock()
    loop.is_running.return_value = True
    channel._loop = loop

    with patch("asyncio.run_coroutine_threadsafe") as submit:
        channel._on_message_sync(MagicMock())
        submit.assert_not_called()


@pytest.mark.asyncio
async def test_on_message_inflight_dropped_after_stop() -> None:
    channel = FeishuChannel(FeishuConfig(), MessageBus())
    channel._running = True
    channel._loop = asyncio.get_running_loop()

    entered = asyncio.Event()
    release = asyncio.Event()

    async def _block_reaction(message_id: str, emoji_type: str = "THUMBSUP") -> None:
        del message_id, emoji_type
        entered.set()
        await release.wait()

    channel._add_reaction = _block_reaction  # type: ignore[method-assign]
    channel._handle_message = MagicMock()

    data = MagicMock()
    data.event.message.message_id = "m1"
    data.event.message.chat_id = "c1"
    data.event.message.chat_type = "group"
    data.event.message.message_type = "text"
    data.event.message.content = '{"text": "hello"}'
    data.event.sender.sender_type = "user"
    data.event.sender.sender_id.open_id = "u1"

    task = asyncio.create_task(channel._on_message(data))
    await asyncio.wait_for(entered.wait(), timeout=1)

    await channel.stop()
    release.set()
    await asyncio.wait_for(task, timeout=1)

    channel._handle_message.assert_not_called()
