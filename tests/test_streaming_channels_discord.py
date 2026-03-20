# ruff: noqa: F403, F405
from __future__ import annotations

from tests._streaming_channels_testkit import *


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


@pytest.mark.asyncio
async def test_discord_send_media_then_text_without_duplicate_reply_reference(tmp_path) -> None:
    channel = DiscordChannel(DiscordConfig(enabled=True, token=SecretStr("x")), MagicMock())
    media_path = tmp_path / "report.txt"
    media_path.write_text("hello", encoding="utf-8")

    http = SimpleNamespace(
        post=AsyncMock(return_value=_DiscordResponse({"id": "file-1"})),
        request=AsyncMock(return_value=_DiscordResponse({"id": "m1"})),
        aclose=AsyncMock(),
    )
    channel._http = cast(httpx.AsyncClient, cast(object, http))

    await channel.send(
        OutboundMessage(
            channel="discord",
            chat_id="123",
            content="final text",
            reply_to="reply-1",
            media=[str(media_path)],
        )
    )

    assert http.post.await_count == 1
    post_kwargs = http.post.await_args.kwargs
    assert (
        post_kwargs["data"]["payload_json"]
        == '{"message_reference": {"message_id": "reply-1"}, "allowed_mentions": {"replied_user": false}}'
    )

    assert http.request.await_count == 1
    request_kwargs = http.request.await_args.kwargs
    assert request_kwargs["json"]["content"] == "final text"
    assert "message_reference" not in request_kwargs["json"]


@pytest.mark.asyncio
async def test_discord_send_failed_media_without_text_falls_back_to_failure_message(tmp_path) -> None:
    channel = DiscordChannel(DiscordConfig(enabled=True, token=SecretStr("x")), MagicMock())
    media_path = tmp_path / "report.txt"
    media_path.write_text("hello", encoding="utf-8")

    http = SimpleNamespace(
        post=AsyncMock(return_value=_DiscordResponse({"retry_after": 1.0}, status_code=429)),
        request=AsyncMock(return_value=_DiscordResponse({"id": "m1"})),
        aclose=AsyncMock(),
    )
    channel._http = cast(httpx.AsyncClient, cast(object, http))

    await channel.send(
        OutboundMessage(
            channel="discord",
            chat_id="123",
            content="",
            media=[str(media_path)],
        )
    )

    assert http.post.await_count == 1
    request_kwargs = http.request.await_args.kwargs
    assert request_kwargs["json"]["content"] == "[attachment: report.txt - send failed]"
