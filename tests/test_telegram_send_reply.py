from __future__ import annotations

import logging
from pathlib import Path
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
        raise AssertionError("builder.proxy should not be called when request proxy is configured")

    def get_updates_proxy(self, _proxy: str):
        raise AssertionError(
            "builder.get_updates_proxy should not be called when request proxy is configured"
        )

    def build(self):
        return self._app


def _make_telegram_update(
    *,
    chat_type: str = "group",
    text: str | None = None,
    caption: str | None = None,
    entities=None,
    caption_entities=None,
    reply_to_message=None,
    photo=None,
    voice=None,
    audio=None,
    document=None,
    message_thread_id: int | None = None,
):
    user = SimpleNamespace(id=123, username="alice", first_name="Alice")
    message = SimpleNamespace(
        chat=SimpleNamespace(type=chat_type, is_forum=chat_type != "private"),
        chat_id=-100123,
        text=text,
        caption=caption,
        entities=entities or [],
        caption_entities=caption_entities or [],
        reply_to_message=reply_to_message,
        photo=photo,
        voice=voice,
        audio=audio,
        document=document,
        media_group_id=None,
        message_thread_id=message_thread_id,
        message_id=77,
    )
    return SimpleNamespace(message=message, effective_user=user)


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


def test_telegram_group_policy_defaults_to_mention() -> None:
    assert TelegramConfig().group_policy == "mention"


def test_telegram_get_extension_preserves_original_document_suffix() -> None:
    channel = TelegramChannel(TelegramConfig(), MagicMock())

    assert channel._get_extension("file", None, "report.pdf") == ".pdf"
    assert channel._get_extension("file", None, "archive.tar.gz") == ".tar.gz"


def test_telegram_derive_topic_session_key() -> None:
    message = SimpleNamespace(
        chat=SimpleNamespace(type="supergroup"),
        chat_id=-100123,
        message_thread_id=42,
    )

    assert TelegramChannel._derive_topic_session_key(message) == "telegram:-100123:topic:42"


@pytest.mark.asyncio
async def test_telegram_progress_send_keeps_message_thread_id() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), MagicMock())
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=321)),
        edit_message_text=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="topic progress",
            metadata={"_progress": True, "message_thread_id": 42},
        )
    )

    await channel._progress_handler.flush("12345", force=True)

    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["message_thread_id"] == 42


@pytest.mark.asyncio
async def test_telegram_reply_inferrs_topic_from_cached_thread_context() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), reply_to_message=True),
        MagicMock(),
    )
    bot = SimpleNamespace(send_message=AsyncMock(), edit_message_text=AsyncMock())
    channel._app = SimpleNamespace(bot=bot)
    channel._message_threads[("12345", 10)] = 42

    await channel.send(
        OutboundMessage(
            channel="telegram",
            chat_id="12345",
            content="hello",
            metadata={"message_id": 10},
        )
    )

    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["message_thread_id"] == 42
    assert kwargs["reply_parameters"].message_id == 10


@pytest.mark.asyncio
async def test_telegram_progress_does_not_stop_typing() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), MagicMock())
    bot = SimpleNamespace(send_message=AsyncMock(), edit_message_text=AsyncMock())
    channel._app = SimpleNamespace(bot=bot)
    channel._typing_tasks["12345"] = AsyncMock()

    with patch.object(channel, "_stop_typing") as stop_typing:
        await channel.send(
            OutboundMessage(
                channel="telegram",
                chat_id="12345",
                content="progress",
                metadata={"_progress": True},
            )
        )

    stop_typing.assert_not_called()


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
        if channel._stop_event is not None:
            channel._stop_event.set()

    fake_updater.start_polling.side_effect = _start_polling

    with patch("bao.channels.telegram.Application.builder", return_value=fake_builder):
        await channel.start()

    assert fake_builder.api_request is not None
    assert fake_builder.poll_request is not None
    assert fake_builder.api_request is not fake_builder.poll_request
    kwargs = fake_updater.start_polling.await_args.kwargs
    assert kwargs["error_callback"] is _on_polling_error


@pytest.mark.asyncio
async def test_telegram_start_configures_proxy_on_requests_only() -> None:
    seen_requests: list[SimpleNamespace] = []

    class _FakeHTTPXRequest:
        def __init__(self, **kwargs) -> None:
            seen_requests.append(SimpleNamespace(**kwargs))

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), proxy="socks5://127.0.0.1:1080"),
        MagicMock(),
    )

    fake_updater = SimpleNamespace(start_polling=AsyncMock())
    fake_app = _build_fake_telegram_app(
        bot=SimpleNamespace(
            initialize=AsyncMock(),
            get_me=AsyncMock(return_value=SimpleNamespace(id=1, username="bot")),
            set_my_commands=AsyncMock(),
        ),
        updater=fake_updater,
    )
    fake_builder = _FakeBuilder(fake_app)

    async def _start_polling(**_kwargs):
        if channel._stop_event is not None:
            channel._stop_event.set()

    fake_updater.start_polling.side_effect = _start_polling

    with (
        patch("bao.channels.telegram.HTTPXRequest", _FakeHTTPXRequest),
        patch("bao.channels.telegram.Application.builder", return_value=fake_builder),
    ):
        await channel.start()

    assert len(seen_requests) == 2
    assert seen_requests[0].proxy == "socks5://127.0.0.1:1080"
    assert seen_requests[1].proxy == "socks5://127.0.0.1:1080"


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


@pytest.mark.asyncio
async def test_telegram_group_policy_mention_ignores_unmentioned_group_message() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), allow_from=["123"], group_policy="mention"),
        MagicMock(),
    )
    channel._app = SimpleNamespace(
        bot=SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(id=999, username="bao_bot")))
    )
    channel._handle_message = AsyncMock()

    await channel._on_message(_make_telegram_update(text="hello everyone"), None)

    channel._handle_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_group_policy_mention_accepts_entity_mention_and_caches_identity() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), allow_from=["123"], group_policy="mention"),
        MagicMock(),
    )
    bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(id=999, username="bao_bot")))
    channel._app = SimpleNamespace(bot=bot)
    channel._handle_message = AsyncMock()

    mention = SimpleNamespace(type="mention", offset=0, length=8)
    await channel._on_message(_make_telegram_update(text="@bao_bot hi", entities=[mention]), None)
    await channel._on_message(_make_telegram_update(text="@bao_bot again", entities=[mention]), None)

    assert channel._handle_message.await_count == 2
    assert bot.get_me.await_count == 1


@pytest.mark.asyncio
async def test_telegram_group_policy_open_accepts_plain_group_message() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), allow_from=["123"], group_policy="open"),
        MagicMock(),
    )
    channel._app = SimpleNamespace(bot=SimpleNamespace(get_me=AsyncMock()))
    channel._handle_message = AsyncMock()

    await channel._on_message(_make_telegram_update(text="hello group"), None)

    channel._handle_message.assert_awaited_once()
    channel._app.bot.get_me.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_forward_command_keeps_topic_session_metadata_without_reply_context() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), MagicMock())
    channel._handle_message = AsyncMock()

    reply = SimpleNamespace(text="older message", message_id=2, from_user=SimpleNamespace(id=1))
    update = _make_telegram_update(text="/new", reply_to_message=reply, message_thread_id=42)

    await channel._forward_command(update, None)

    kwargs = channel._handle_message.await_args.kwargs
    assert kwargs["content"] == "/new"
    assert kwargs["metadata"]["session_key"] == "telegram:-100123:topic:42"
    assert kwargs["metadata"]["reply_to_message_id"] == 2


@pytest.mark.asyncio
async def test_telegram_on_message_adds_reply_text_context() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), allow_from=["123"], group_policy="open"),
        MagicMock(),
    )
    channel._app = SimpleNamespace(bot=SimpleNamespace(get_me=AsyncMock(), send_chat_action=AsyncMock()))
    channel._handle_message = AsyncMock()

    reply = SimpleNamespace(text="Hello", caption=None, message_id=2, from_user=SimpleNamespace(id=1))
    await channel._on_message(_make_telegram_update(text="translate this", reply_to_message=reply), None)

    kwargs = channel._handle_message.await_args.kwargs
    assert kwargs["content"].startswith("[Reply to: Hello]")
    assert "translate this" in kwargs["content"]


@pytest.mark.asyncio
async def test_telegram_on_message_attaches_reply_media_and_caption(monkeypatch, tmp_path) -> None:
    media_dir = tmp_path / "telegram"
    media_dir.mkdir(parents=True)
    monkeypatch.setattr("bao.channels.telegram.get_media_path", lambda: media_dir)

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), allow_from=["123"], group_policy="open"),
        MagicMock(),
    )
    bot = SimpleNamespace(
        get_me=AsyncMock(),
        get_file=AsyncMock(return_value=SimpleNamespace(download_to_drive=AsyncMock(return_value=None))),
        send_chat_action=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)
    channel._handle_message = AsyncMock()

    reply = SimpleNamespace(
        text=None,
        caption="A cute cat",
        photo=[SimpleNamespace(file_id="cat_fid", mime_type="image/jpeg")],
        document=None,
        voice=None,
        audio=None,
        video=None,
        video_note=None,
        animation=None,
        message_id=2,
        from_user=SimpleNamespace(id=1),
    )
    await channel._on_message(_make_telegram_update(text="what breed is this?", reply_to_message=reply), None)

    kwargs = channel._handle_message.await_args.kwargs
    assert "[Reply to: A cute cat]" in kwargs["content"]
    assert len(kwargs["media"]) == 1
    assert Path(kwargs["media"][0]).name.startswith("cat_fid")


@pytest.mark.asyncio
async def test_telegram_on_message_uses_reply_media_placeholder_when_no_reply_text(monkeypatch, tmp_path) -> None:
    media_dir = tmp_path / "telegram"
    media_dir.mkdir(parents=True)
    monkeypatch.setattr("bao.channels.telegram.get_media_path", lambda: media_dir)

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), allow_from=["123"], group_policy="open"),
        MagicMock(),
    )
    bot = SimpleNamespace(
        get_me=AsyncMock(),
        get_file=AsyncMock(return_value=SimpleNamespace(download_to_drive=AsyncMock(return_value=None))),
        send_chat_action=AsyncMock(),
    )
    channel._app = SimpleNamespace(bot=bot)
    channel._handle_message = AsyncMock()

    reply = SimpleNamespace(
        text=None,
        caption=None,
        photo=[SimpleNamespace(file_id="reply_photo_fid", mime_type="image/jpeg")],
        document=None,
        voice=None,
        audio=None,
        video=None,
        video_note=None,
        animation=None,
        message_id=2,
        from_user=SimpleNamespace(id=1),
    )
    await channel._on_message(_make_telegram_update(text="what is the image?", reply_to_message=reply), None)

    kwargs = channel._handle_message.await_args.kwargs
    assert kwargs["content"].startswith("[Reply to: [image:")
    assert len(kwargs["media"]) == 1


@pytest.mark.asyncio
async def test_telegram_on_message_reply_media_download_failure_skips_reply_tag() -> None:
    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), allow_from=["123"], group_policy="open"),
        MagicMock(),
    )
    channel._app = SimpleNamespace(
        bot=SimpleNamespace(get_me=AsyncMock(), get_file=None, send_chat_action=AsyncMock())
    )
    channel._handle_message = AsyncMock()

    reply = SimpleNamespace(
        text=None,
        caption=None,
        photo=[SimpleNamespace(file_id="x", mime_type="image/jpeg")],
        document=None,
        voice=None,
        audio=None,
        video=None,
        video_note=None,
        animation=None,
        message_id=2,
        from_user=SimpleNamespace(id=1),
    )
    await channel._on_message(_make_telegram_update(text="what is this?", reply_to_message=reply), None)

    kwargs = channel._handle_message.await_args.kwargs
    assert kwargs["content"] == "what is this?"
    assert kwargs["media"] == []
