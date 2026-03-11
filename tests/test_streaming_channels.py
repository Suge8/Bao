from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import SecretStr
from slack_sdk.web.async_client import AsyncWebClient

import bao.channels.feishu as feishu_module
from bao.bus.events import OutboundMessage
from bao.channels.discord import DiscordChannel
from bao.channels.feishu import FeishuChannel
from bao.channels.slack import SlackChannel
from bao.config.schema import DiscordConfig, FeishuConfig, SlackConfig


@pytest.mark.asyncio
async def test_slack_progress_updates_same_message() -> None:
    channel = SlackChannel(
        SlackConfig(enabled=True, bot_token=SecretStr("x"), app_token=SecretStr("y")),
        MagicMock(),
    )
    web = SimpleNamespace(
        chat_postMessage=AsyncMock(return_value={"ts": "1700000000.1"}),
        chat_update=AsyncMock(),
        files_upload_v2=AsyncMock(),
    )
    channel._web_client = cast(AsyncWebClient, cast(object, web))

    progress = "这是 Slack 上一段足够长的流式进度内容，会先被创建出来。"
    final = f"{progress}然后收口成最终答案。"

    await channel.send(
        OutboundMessage(
            channel="slack",
            chat_id="C1",
            content=progress,
            metadata={"_progress": True, "slack": {"thread_ts": "t1", "channel_type": "channel"}},
        )
    )
    await channel.send(
        OutboundMessage(
            channel="slack",
            chat_id="C1",
            content=final,
            metadata={"slack": {"thread_ts": "t1", "channel_type": "channel"}},
        )
    )

    assert web.chat_postMessage.await_count == 1
    assert web.chat_update.await_count == 1
    assert web.chat_update.await_args.kwargs["ts"] == "1700000000.1"


@pytest.mark.asyncio
async def test_slack_start_waits_until_stop(monkeypatch) -> None:
    channel = SlackChannel(
        SlackConfig(enabled=True, bot_token=SecretStr("x"), app_token=SecretStr("y")),
        MagicMock(),
    )
    web = SimpleNamespace(auth_test=AsyncMock(return_value={"user_id": "U1"}))
    socket_client = SimpleNamespace(
        socket_mode_request_listeners=[],
        connect=AsyncMock(),
        close=AsyncMock(),
    )
    monkeypatch.setattr("bao.channels.slack.AsyncWebClient", lambda token: web)
    monkeypatch.setattr("bao.channels.slack.SocketModeClient", lambda **_kwargs: socket_client)

    start_task = asyncio.create_task(channel.start())
    await asyncio.sleep(0)
    assert not start_task.done()

    await channel.stop()
    await asyncio.wait_for(start_task, timeout=0.5)

    socket_client.connect.assert_awaited_once()
    socket_client.close.assert_awaited_once()


class _DiscordResponse:
    def __init__(self, data: dict[str, object], status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return self._data

    def raise_for_status(self) -> None:
        return None


@pytest.mark.asyncio
async def test_discord_progress_updates_same_message() -> None:
    channel = DiscordChannel(DiscordConfig(enabled=True, token=SecretStr("x")), MagicMock())
    http = SimpleNamespace(
        request=AsyncMock(
            side_effect=[
                _DiscordResponse({"id": "m1"}),
                _DiscordResponse({"id": "m1"}),
            ]
        ),
        aclose=AsyncMock(),
    )
    channel._http = cast(httpx.AsyncClient, cast(object, http))

    progress = "这是 Discord 上一段足够长的流式进度内容，会先被创建出来。"
    final = f"{progress}然后收口成最终答案。"

    await channel.send(
        OutboundMessage(
            channel="discord",
            chat_id="123",
            content=progress,
            metadata={"_progress": True},
        )
    )
    await channel.send(OutboundMessage(channel="discord", chat_id="123", content=final))

    first = http.request.await_args_list[0].args
    second = http.request.await_args_list[1].args
    assert first[0] == "POST"
    assert second[0] == "PATCH"


class _Builder:
    def __init__(self) -> None:
        self._values: dict[str, object] = {}

    def receive_id_type(self, value: str) -> _Builder:
        self._values["receive_id_type"] = value
        return self

    def receive_id(self, value: str) -> _Builder:
        self._values["receive_id"] = value
        return self

    def msg_type(self, value: str) -> _Builder:
        self._values["msg_type"] = value
        return self

    def content(self, value: str) -> _Builder:
        self._values["content"] = value
        return self

    def request_body(self, value: object) -> _Builder:
        self._values["request_body"] = value
        return self

    def message_id(self, value: str) -> _Builder:
        self._values["message_id"] = value
        return self

    def build(self) -> SimpleNamespace:
        return SimpleNamespace(**self._values)


class _BuilderFactory:
    @staticmethod
    def builder() -> _Builder:
        return _Builder()


class _FeishuResponse:
    def __init__(self, *, message_id: str | None = None) -> None:
        self.data = SimpleNamespace(message_id=message_id)
        self.code = 0
        self.msg = "ok"

    def success(self) -> bool:
        return True

    def get_log_id(self) -> str:
        return "log-id"


@pytest.mark.asyncio
async def test_feishu_progress_updates_same_message(monkeypatch) -> None:
    monkeypatch.setattr(feishu_module, "CreateMessageRequest", _BuilderFactory)
    monkeypatch.setattr(feishu_module, "CreateMessageRequestBody", _BuilderFactory)
    monkeypatch.setattr(feishu_module, "PatchMessageRequest", _BuilderFactory)
    monkeypatch.setattr(feishu_module, "PatchMessageRequestBody", _BuilderFactory)

    created: list[str] = []
    patched: list[str] = []

    def _create(request: SimpleNamespace) -> _FeishuResponse:
        created.append(request.request_body.content)
        return _FeishuResponse(message_id="om_1")

    def _patch(request: SimpleNamespace) -> _FeishuResponse:
        patched.append(request.request_body.content)
        return _FeishuResponse(message_id="om_1")

    channel = FeishuChannel(
        FeishuConfig(enabled=True, app_id="app", app_secret=SecretStr("secret")),
        MagicMock(),
    )
    channel._client = SimpleNamespace(
        im=SimpleNamespace(
            v1=SimpleNamespace(message=SimpleNamespace(create=_create, patch=_patch))
        )
    )

    progress = "这是 Feishu 上一段足够长的流式进度内容，会先被创建出来。"
    final = f"{progress}然后收口成最终答案。"

    await channel.send(
        OutboundMessage(
            channel="feishu",
            chat_id="ou_xxx",
            content=progress,
            metadata={"_progress": True},
        )
    )
    await channel.send(OutboundMessage(channel="feishu", chat_id="ou_xxx", content=final))

    assert len(created) == 1
    assert len(patched) == 1


@pytest.mark.asyncio
async def test_feishu_start_waits_until_stop(monkeypatch) -> None:
    started = threading.Event()
    released = threading.Event()

    class _FakeLarkClientBuilder:
        def app_id(self, _value: str):
            return self

        def app_secret(self, _value: str):
            return self

        def log_level(self, _value: object):
            return self

        def build(self) -> SimpleNamespace:
            return SimpleNamespace()

    class _FakeEventDispatcherBuilder:
        def register_p2_im_message_receive_v1(self, _handler):
            return self

        def build(self) -> SimpleNamespace:
            return SimpleNamespace()

    class _FakeWsClient:
        def start(self) -> None:
            started.set()
            released.wait(timeout=1)

        def stop(self) -> None:
            released.set()

    monkeypatch.setattr(feishu_module, "FEISHU_AVAILABLE", True)
    monkeypatch.setattr(
        feishu_module,
        "lark",
        SimpleNamespace(
            LogLevel=SimpleNamespace(INFO="INFO"),
            Client=SimpleNamespace(builder=lambda: _FakeLarkClientBuilder()),
            EventDispatcherHandler=SimpleNamespace(
                builder=lambda *_args: _FakeEventDispatcherBuilder()
            ),
            ws=SimpleNamespace(Client=lambda *_args, **_kwargs: _FakeWsClient()),
        ),
    )

    channel = FeishuChannel(
        FeishuConfig(enabled=True, app_id="app", app_secret=SecretStr("secret")),
        MagicMock(),
    )

    start_task = asyncio.create_task(channel.start())
    await asyncio.to_thread(started.wait, 0.5)
    assert started.is_set()
    assert not start_task.done()

    await channel.stop()
    await asyncio.wait_for(start_task, timeout=0.5)
