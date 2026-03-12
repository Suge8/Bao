import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels.feishu import FeishuChannel, _extract_interactive_content, _extract_post_text
from bao.config.schema import FeishuConfig


def _make_feishu_channel() -> FeishuChannel:
    channel = FeishuChannel(FeishuConfig(enabled=True, app_id="app", app_secret="secret"), MessageBus())
    channel._client = object()
    return channel


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


def test_feishu_detect_msg_format_prefers_text_for_short_plain_content() -> None:
    channel = FeishuChannel(FeishuConfig(), MessageBus())

    assert channel._detect_msg_format("hello bao") == "text"


def test_feishu_detect_msg_format_uses_post_for_markdown_link() -> None:
    channel = FeishuChannel(FeishuConfig(), MessageBus())

    assert channel._detect_msg_format("看看 [Bao](https://example.com)") == "post"


def test_feishu_detect_msg_format_uses_interactive_for_structured_markdown() -> None:
    channel = FeishuChannel(FeishuConfig(), MessageBus())

    assert channel._detect_msg_format("## 标题\n\n**重点**") == "interactive"


def test_feishu_markdown_to_post_keeps_link_segments() -> None:
    payload = FeishuChannel._markdown_to_post("看看 [Bao](https://example.com)\n第二行")

    first_line = payload["zh_cn"]["content"][0]
    assert first_line[0] == {"tag": "text", "text": "看看 "}
    assert first_line[1] == {"tag": "a", "text": "Bao", "href": "https://example.com"}
    assert payload["zh_cn"]["content"][1] == [{"tag": "text", "text": "第二行"}]


@pytest.mark.asyncio
async def test_feishu_send_plain_text_uses_text_message() -> None:
    channel = _make_feishu_channel()
    channel._send_json_message = AsyncMock(return_value="om_text")  # type: ignore[method-assign]
    channel._send_interactive_elements = AsyncMock()  # type: ignore[method-assign]

    await channel.send(OutboundMessage(channel="feishu", chat_id="ou_1", content="hello bao"))

    channel._send_json_message.assert_awaited_once_with(
        "ou_1",
        "text",
        {"text": "hello bao"},
    )
    channel._send_interactive_elements.assert_not_awaited()


@pytest.mark.asyncio
async def test_feishu_send_markdown_link_uses_post_message() -> None:
    channel = _make_feishu_channel()
    channel._send_json_message = AsyncMock(return_value="om_post")  # type: ignore[method-assign]
    channel._send_interactive_elements = AsyncMock()  # type: ignore[method-assign]

    await channel.send(
        OutboundMessage(
            channel="feishu",
            chat_id="ou_1",
            content="看看 [Bao](https://example.com)",
        )
    )

    args = channel._send_json_message.await_args.args
    assert args[0] == "ou_1"
    assert args[1] == "post"
    assert args[2]["zh_cn"]["content"][0][1] == {
        "tag": "a",
        "text": "Bao",
        "href": "https://example.com",
    }
    channel._send_interactive_elements.assert_not_awaited()


@pytest.mark.asyncio
async def test_feishu_send_structured_markdown_uses_interactive_message() -> None:
    channel = _make_feishu_channel()
    channel._send_json_message = AsyncMock()  # type: ignore[method-assign]
    channel._send_interactive_elements = AsyncMock(return_value="om_card")  # type: ignore[method-assign]

    await channel.send(
        OutboundMessage(channel="feishu", chat_id="ou_1", content="## 标题\n\n**重点**")
    )

    channel._send_json_message.assert_not_awaited()
    channel._send_interactive_elements.assert_awaited_once()


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
    channel = FeishuChannel(FeishuConfig(group_policy="open"), MessageBus())
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
