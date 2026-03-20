from __future__ import annotations

from types import SimpleNamespace

from bao.channels.telegram import TelegramChannel


def test_telegram_get_extension_preserves_original_document_suffix() -> None:
    channel = TelegramChannel(None, None)  # type: ignore[arg-type]

    assert channel._get_extension("file", None, "report.pdf") == ".pdf"
    assert channel._get_extension("file", None, "archive.tar.gz") == ".tar.gz"


def test_telegram_derive_topic_session_key() -> None:
    message = SimpleNamespace(
        chat=SimpleNamespace(type="supergroup"),
        chat_id=-100123,
        message_thread_id=42,
    )

    assert TelegramChannel._derive_topic_session_key(message) == "telegram:-100123:topic:42"
