from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from pydantic import SecretStr

from bao.channels.telegram import TelegramChannel
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


@dataclass(slots=True)
class TelegramUpdateOptions:
    chat_type: str = "group"
    text: str | None = None
    caption: str | None = None
    entities: list[object] = field(default_factory=list)
    caption_entities: list[object] = field(default_factory=list)
    reply_to_message: object | None = None
    photo: object | None = None
    voice: object | None = None
    audio: object | None = None
    document: object | None = None
    message_thread_id: int | None = None


def _make_telegram_update(options: TelegramUpdateOptions) -> SimpleNamespace:
    user = SimpleNamespace(id=123, username="alice", first_name="Alice")
    message = SimpleNamespace(
        chat=SimpleNamespace(type=options.chat_type, is_forum=options.chat_type != "private"),
        chat_id=-100123,
        text=options.text,
        caption=options.caption,
        entities=options.entities,
        caption_entities=options.caption_entities,
        reply_to_message=options.reply_to_message,
        photo=options.photo,
        voice=options.voice,
        audio=options.audio,
        document=options.document,
        media_group_id=None,
        message_thread_id=options.message_thread_id,
        message_id=77,
    )
    return SimpleNamespace(message=message, effective_user=user)


def build_channel(**config_kwargs) -> TelegramChannel:
    config = TelegramConfig(enabled=True, token=SecretStr("t"), **config_kwargs)
    return TelegramChannel(config, MagicMock())
