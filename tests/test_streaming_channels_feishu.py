# ruff: noqa: F403, F405
from __future__ import annotations

from tests._streaming_channels_testkit import *


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
