from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr
from telegram.error import BadRequest, NetworkError

from bao.bus.events import OutboundMessage
from bao.channels.telegram import _UPDATER_CLEANUP_LOG, TelegramChannel, _on_polling_error
from bao.config.schema import TelegramConfig


def _build_fake_telegram_app(*, bot: SimpleNamespace, updater: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        add_error_handler=MagicMock(),
        add_handler=MagicMock(),
        initialize=AsyncMock(),
        start=AsyncMock(),
        bot=bot,
        updater=updater,
    )


class _FakeBuilder:
    def __init__(self, app: SimpleNamespace) -> None:
        self.api_request = None
        self.poll_request = None
        self._app = app

    def token(self, _token: str):
        return self

    def request(self, req):
        self.api_request = req
        return self

    def get_updates_request(self, req):
        self.poll_request = req
        return self

    def proxy(self, _proxy: str):
        return self

    def get_updates_proxy(self, _proxy: str):
        return self

    def build(self):
        return self._app


@pytest.mark.asyncio
async def test_telegram_send_prefers_reply_to_over_metadata() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), reply_to_message=True), MagicMock()
    )
    bot = SimpleNamespace(send_message=AsyncMock())
    channel._app = SimpleNamespace(bot=bot)

    msg = OutboundMessage(
        channel="telegram",
        chat_id="12345",
        content="hello",
        reply_to="77",
        metadata={"message_id": "999"},
    )
    await channel.send(msg)

    assert bot.send_message.await_count == 1
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 12345
    assert kwargs["reply_parameters"].message_id == 77


@pytest.mark.asyncio
async def test_telegram_send_ignores_bool_reply_to() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), reply_to_message=True), MagicMock()
    )
    bot = SimpleNamespace(send_message=AsyncMock())
    channel._app = SimpleNamespace(bot=bot)

    msg = OutboundMessage(
        channel="telegram",
        chat_id="12345",
        content="hello",
        reply_to=cast(str | None, cast(object, True)),
    )
    await channel.send(msg)

    assert bot.send_message.await_count == 1
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 12345
    assert kwargs["reply_parameters"] is None


@pytest.mark.asyncio
async def test_telegram_progress_is_buffered_before_final_send() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), MagicMock())
    bot = SimpleNamespace(send_message=AsyncMock(), edit_message_text=AsyncMock())
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="你",
            metadata={"_progress": True},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="好",
            metadata={"_progress": True},
        )
    )

    assert bot.send_message.await_count == 0
    assert bot.edit_message_text.await_count == 0

    await channel.send(OutboundMessage(channel="telegram", chat_id="12345", content="你好"))

    assert bot.send_message.await_count == 1
    assert bot.edit_message_text.await_count == 0
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 12345
    assert kwargs["text"] == "你好"


@pytest.mark.asyncio
async def test_telegram_final_only_sends_tail_after_progress_flush() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), MagicMock())
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
        edit_message_text=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    progress = "这是一个足够长的进度句子，会先发出去，顺手把上下文也先梳理一下。"
    final = f"{progress}然后再补一句结论。"

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content=progress,
            metadata={"_progress": True},
        )
    )
    await channel.send(OutboundMessage(channel="telegram", chat_id="12345", content=final))

    assert bot.send_message.await_count == 1
    assert bot.edit_message_text.await_count == 1
    first = bot.send_message.await_args_list[0].kwargs
    second = bot.edit_message_text.await_args_list[0].kwargs
    assert first["text"] == progress
    assert second["message_id"] == 321
    assert second["text"] == final


@pytest.mark.asyncio
async def test_telegram_tool_hint_starts_new_editable_turn() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), MagicMock())
    bot = SimpleNamespace(
        send_message=AsyncMock(
            side_effect=[
                SimpleNamespace(message_id=321),
                SimpleNamespace(message_id=654),
                SimpleNamespace(message_id=987),
            ]
        ),
        edit_message_text=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="我现在去看看。",
            metadata={"_progress": True},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="🔎 Search Web: latest ai news",
            metadata={"_progress": True, "_tool_hint": True},
        )
    )
    await channel.send(
        OutboundMessage(channel="telegram", chat_id="12345", content="整理好了，这是最终答案。")
    )

    assert bot.send_message.await_count == 3
    assert bot.edit_message_text.await_count == 0
    first_send = bot.send_message.await_args_list[0].kwargs
    second_send = bot.send_message.await_args_list[1].kwargs
    third_send = bot.send_message.await_args_list[2].kwargs
    assert first_send["text"] == "我现在去看看。"
    assert second_send["text"] == "🔎 Search Web: latest ai news"
    assert third_send["text"] == "整理好了，这是最终答案。"


@pytest.mark.asyncio
async def test_telegram_network_error_does_not_fallback_to_plain_resend() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), MagicMock())
    bot = SimpleNamespace(
        send_message=AsyncMock(side_effect=NetworkError("httpx.ConnectError")),
        edit_message_text=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    with pytest.raises(NetworkError):
        await channel.send(
            OutboundMessage(
                channel="telegram",
                chat_id="12345",
                content="这是一个足够长的进度句子，会先发出去，顺手把上下文也先梳理一下。",
                metadata={"_progress": True},
            )
        )

    assert bot.send_message.await_count == 1
    assert bot.edit_message_text.await_count == 0


@pytest.mark.asyncio
async def test_telegram_parse_error_falls_back_to_plain_send_once() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), MagicMock())
    bot = SimpleNamespace(
        send_message=AsyncMock(
            side_effect=[
                BadRequest("Can't parse entities"),
                SimpleNamespace(message_id=99),
            ]
        ),
        edit_message_text=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="**这是一个足够长的 Markdown 进度句子，会先触发 HTML 发送。**",
            metadata={"_progress": True},
        )
    )

    assert bot.send_message.await_count == 2
    first = bot.send_message.await_args_list[0].kwargs
    second = bot.send_message.await_args_list[1].kwargs
    assert first["parse_mode"] == "HTML"
    assert "parse_mode" not in second


@pytest.mark.asyncio
async def test_telegram_edit_network_error_is_not_retried_as_plain_text() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), MagicMock())
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
        edit_message_text=AsyncMock(side_effect=NetworkError("httpx.ConnectError")),
    )
    channel._app = SimpleNamespace(bot=bot)

    progress = "这是一个足够长的进度句子，会先发出去，顺手把上下文也先梳理一下。"
    final = f"{progress}然后再补一句结论。"

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content=progress,
            metadata={"_progress": True},
        )
    )

    with pytest.raises(NetworkError):
        await channel.send(OutboundMessage(channel="telegram", chat_id="12345", content=final))

    assert bot.send_message.await_count == 1
    assert bot.edit_message_text.await_count == 1


@pytest.mark.asyncio
async def test_telegram_edit_message_not_modified_is_ignored() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), MagicMock())
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
        edit_message_text=AsyncMock(side_effect=BadRequest("Message is not modified")),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel._update_progress_text("12345", 321, "相同文本")

    assert bot.send_message.await_count == 0
    assert bot.edit_message_text.await_count == 1


@pytest.mark.asyncio
async def test_telegram_start_uses_separate_requests_for_polling_and_api() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), MagicMock())

    fake_updater = SimpleNamespace(start_polling=AsyncMock())
    fake_app = _build_fake_telegram_app(
        bot=SimpleNamespace(
            initialize=AsyncMock(),
            get_me=AsyncMock(return_value=SimpleNamespace(username="bot")),
            set_my_commands=AsyncMock(),
        ),
        updater=fake_updater,
    )
    fake_builder = _FakeBuilder(fake_app)

    async def _start_polling(**_kwargs):
        channel._running = False

    fake_updater.start_polling.side_effect = _start_polling

    with patch("bao.channels.telegram.Application.builder", return_value=fake_builder):
        await channel.start()

    assert fake_builder.api_request is not None
    assert fake_builder.poll_request is not None
    assert fake_builder.api_request is not fake_builder.poll_request
    kwargs = fake_updater.start_polling.await_args.kwargs
    assert kwargs["error_callback"] is _on_polling_error


@pytest.mark.asyncio
async def test_telegram_start_error_includes_failed_phase() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), MagicMock())

    fake_updater = SimpleNamespace(start_polling=AsyncMock())
    fake_app = _build_fake_telegram_app(
        bot=SimpleNamespace(
            initialize=AsyncMock(side_effect=NetworkError("httpx.ConnectError")),
            get_me=AsyncMock(),
            set_my_commands=AsyncMock(),
        ),
        updater=fake_updater,
    )
    with patch("bao.channels.telegram.Application.builder", return_value=_FakeBuilder(fake_app)):
        with pytest.raises(RuntimeError, match="bot_initialize: NetworkError"):
            await channel.start()


@pytest.mark.asyncio
async def test_telegram_stop_skips_non_running_updater() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), MagicMock())
    updater = SimpleNamespace(running=False, stop=AsyncMock())
    app = SimpleNamespace(updater=updater, stop=AsyncMock(), shutdown=AsyncMock())
    channel._app = app

    await channel.stop()

    updater.stop.assert_not_awaited()
    app.stop.assert_awaited_once()
    app.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_telegram_stop_suppresses_known_updater_cleanup_log() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), MagicMock())
    updater = SimpleNamespace(running=True, stop=AsyncMock())
    app = SimpleNamespace(updater=updater, stop=AsyncMock(), shutdown=AsyncMock())
    channel._app = app

    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    ext_logger = logging.getLogger("telegram.ext.Updater")
    handler = _Capture()
    ext_logger.addHandler(handler)
    try:

        async def _stop() -> None:
            ext_logger.error(_UPDATER_CLEANUP_LOG)

        updater.stop.side_effect = _stop
        await channel.stop()
    finally:
        ext_logger.removeHandler(handler)

    assert records == []
    updater.stop.assert_awaited_once()


def test_telegram_polling_error_callback_logs_network_issue_without_traceback() -> None:
    with patch("bao.channels.telegram.logger.warning") as warning:
        _on_polling_error(NetworkError("httpx.ConnectError"))

    warning.assert_called_once()
