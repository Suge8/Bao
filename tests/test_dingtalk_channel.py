from unittest.mock import AsyncMock

import pytest

from bao.bus.queue import MessageBus
from bao.channels.dingtalk import DingTalkChannel
from bao.config.schema import DingTalkConfig


def test_guess_upload_type_by_extension() -> None:
    channel = DingTalkChannel(DingTalkConfig(), MessageBus())
    assert channel._guess_upload_type("https://a/b/c.jpg") == "image"
    assert channel._guess_upload_type("/tmp/voice.amr") == "voice"
    assert channel._guess_upload_type("file:///tmp/video.mp4") == "video"
    assert channel._guess_upload_type("/tmp/data.bin") == "file"


def test_guess_filename_with_fallback() -> None:
    channel = DingTalkChannel(DingTalkConfig(), MessageBus())
    assert channel._guess_filename("https://a/b/c.png", "image") == "c.png"
    assert channel._guess_filename("https://a/", "image") == "image.jpg"
    assert channel._guess_filename("https://a/", "voice") == "audio.amr"
    assert channel._guess_filename("https://a/", "video") == "video.mp4"
    assert channel._guess_filename("https://a/", "file") == "file.bin"


def test_is_http_url_supports_http_https_only() -> None:
    assert DingTalkChannel._is_http_url("http://example.com") is True
    assert DingTalkChannel._is_http_url("https://example.com") is True
    assert DingTalkChannel._is_http_url("file:///tmp/a.txt") is False


def test_resolve_local_media_path_windows_drive_file_uri() -> None:
    path = DingTalkChannel._resolve_local_media_path(
        "file:///C:/Users/Alice/My%20Docs/file.txt",
        os_name="nt",
    )
    assert str(path) == "C:/Users/Alice/My Docs/file.txt"


def test_resolve_local_media_path_windows_unc_file_uri() -> None:
    path = DingTalkChannel._resolve_local_media_path(
        "file://server/share/my%20file.txt",
        os_name="nt",
    )
    assert str(path) == "//server/share/my file.txt"


@pytest.mark.asyncio
async def test_send_media_ref_keeps_image_url_payload_shape() -> None:
    channel = DingTalkChannel(DingTalkConfig(), MessageBus())
    channel._send_batch_message = AsyncMock(return_value=True)

    ok = await channel._send_media_ref(
        token="tok",
        chat_id="u1",
        media_ref="https://example.com/a.jpg",
    )

    assert ok is True
    channel._send_batch_message.assert_awaited_once_with(
        "tok",
        "u1",
        "sampleImageMsg",
        {"photoURL": "https://example.com/a.jpg"},
    )


@pytest.mark.asyncio
async def test_send_media_ref_uploaded_image_uses_sample_file_payload() -> None:
    channel = DingTalkChannel(DingTalkConfig(), MessageBus())
    channel._read_media_bytes = AsyncMock(return_value=(b"x", "pic.jpeg", "image/jpeg"))
    channel._upload_media = AsyncMock(return_value="mid_123")
    channel._send_batch_message = AsyncMock(return_value=True)

    ok = await channel._send_media_ref(token="tok", chat_id="u1", media_ref="/tmp/pic.jpeg")

    assert ok is True
    channel._send_batch_message.assert_awaited_once_with(
        "tok",
        "u1",
        "sampleFile",
        {"mediaId": "mid_123", "fileName": "pic.jpeg", "fileType": "jpg"},
    )
