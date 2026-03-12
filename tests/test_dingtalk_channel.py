from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
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


@pytest.mark.asyncio
async def test_send_batch_message_routes_group_chat_to_group_endpoint() -> None:
    channel = DingTalkChannel(DingTalkConfig(client_id="robot"), MessageBus())
    channel._http = SimpleNamespace(
        post=AsyncMock(
            return_value=SimpleNamespace(
                status_code=200,
                text="{}",
                json=lambda: {},
            )
        )
    )

    ok = await channel._send_batch_message("tok", "group:cid_1", "sampleMarkdown", {"text": "hi"})

    assert ok is True
    kwargs = channel._http.post.await_args.kwargs
    assert kwargs["json"]["openConversationId"] == "cid_1"
    assert kwargs["json"]["msgKey"] == "sampleMarkdown"


@pytest.mark.asyncio
async def test_on_message_routes_group_reply_back_to_group_chat_id() -> None:
    channel = DingTalkChannel(DingTalkConfig(), MessageBus())
    channel._handle_message = AsyncMock()

    await channel._on_message(
        "hello",
        "user_1",
        "Alice",
        conversation_type="2",
        conversation_id="cid_1",
    )

    kwargs = channel._handle_message.await_args.kwargs
    assert kwargs["sender_id"] == "user_1"
    assert kwargs["chat_id"] == "group:cid_1"
    assert kwargs["metadata"]["conversation_type"] == "2"
    assert kwargs["metadata"]["conversation_id"] == "cid_1"


@pytest.mark.asyncio
async def test_start_handler_uses_voice_recognition_when_text_is_empty(monkeypatch) -> None:
    registered: dict[str, object] = {}

    class _AckMessage:
        STATUS_OK = 0

    class _CallbackHandler:
        pass

    class _Credential:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    class _DingTalkStreamClient:
        def __init__(self, _credential) -> None:
            self.registered_handler = None

        def register_callback_handler(self, topic, handler) -> None:
            registered["topic"] = topic
            registered["handler"] = handler

        async def start(self) -> None:
            return None

    class _ChatbotMessage:
        TOPIC = "chatbot"

        @staticmethod
        def from_dict(raw):
            return SimpleNamespace(
                text=SimpleNamespace(content=(raw.get("text") or {}).get("content", "")),
                sender_staff_id=raw.get("senderStaffId"),
                sender_id=raw.get("senderId"),
                sender_nick=raw.get("senderNick"),
            )

    monkeypatch.setitem(
        sys.modules,
        "dingtalk_stream",
        SimpleNamespace(
            AckMessage=_AckMessage,
            CallbackHandler=_CallbackHandler,
            Credential=_Credential,
            DingTalkStreamClient=_DingTalkStreamClient,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "dingtalk_stream.chatbot",
        SimpleNamespace(ChatbotMessage=_ChatbotMessage),
    )
    monkeypatch.setattr("bao.channels.dingtalk.DINGTALK_AVAILABLE", True)

    channel = DingTalkChannel(
        DingTalkConfig(client_id="robot", client_secret="secret"),
        MessageBus(),
    )
    channel._run_reconnect_loop = AsyncMock()
    channel._on_message = AsyncMock()

    await channel.start()

    handler = registered["handler"]
    ack = await handler.process(
        SimpleNamespace(
            data={
                "text": {"content": ""},
                "extensions": {"content": {"recognition": "voice text"}},
                "senderStaffId": "user_1",
                "senderNick": "Alice",
                "conversationType": "2",
                "conversationId": "cid_1",
            }
        )
    )

    assert ack == (_AckMessage.STATUS_OK, "OK")
    await asyncio.sleep(0)
    channel._on_message.assert_awaited_once_with("voice text", "user_1", "Alice", "2", "cid_1")
