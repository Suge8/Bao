from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr
from telegram.error import NetworkError

from bao.channels.telegram import _UPDATER_CLEANUP_LOG, TelegramChannel, _on_polling_error
from bao.config.schema import TelegramConfig
from tests._telegram_channel_testkit import _build_fake_telegram_app, _FakeBuilder


def test_telegram_register_handlers_uses_core_command_registry() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), SimpleNamespace())
    app = SimpleNamespace(add_error_handler=MagicMock(), add_handler=MagicMock())

    channel._register_handlers(app)

    command_sets = [
        handler.args[0].commands
        for handler in app.add_handler.call_args_list
        if hasattr(handler.args[0], "commands")
    ]
    assert frozenset({"memory"}) in command_sets
    assert frozenset({"model"}) in command_sets


@pytest.mark.asyncio
async def test_telegram_start_uses_separate_requests_for_polling_and_api() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), SimpleNamespace())

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
    command_names = [command.command for command in fake_app.bot.set_my_commands.await_args.args[0]]
    assert "memory" in command_names
    assert "model" in command_names



@pytest.mark.asyncio
async def test_telegram_start_configures_proxy_on_requests_only() -> None:
    seen_requests: list[SimpleNamespace] = []

    class _FakeHTTPXRequest:
        def __init__(self, **kwargs) -> None:
            seen_requests.append(SimpleNamespace(**kwargs))

    channel = TelegramChannel(
        TelegramConfig(enabled=True, token=SecretStr("t"), proxy="socks5://127.0.0.1:1080"),
        SimpleNamespace(),
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
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), SimpleNamespace())

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
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), SimpleNamespace())
    updater = SimpleNamespace(running=False, stop=AsyncMock())
    app = SimpleNamespace(updater=updater, stop=AsyncMock(), shutdown=AsyncMock())
    channel._app = app

    await channel.stop()

    updater.stop.assert_not_awaited()
    app.stop.assert_awaited_once()
    app.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_telegram_stop_suppresses_known_updater_cleanup_log() -> None:
    channel = TelegramChannel(TelegramConfig(enabled=True, token=SecretStr("t")), SimpleNamespace())
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
