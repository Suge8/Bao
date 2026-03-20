# ruff: noqa: F403, F405
from __future__ import annotations

from tests._streaming_channels_testkit import *


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
