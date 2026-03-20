# ruff: noqa: F401
from __future__ import annotations

from datetime import date
from email.message import EmailMessage

import pytest

from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels.email import EmailChannel
from bao.config.schema import EmailConfig


def _make_config() -> EmailConfig:
    return EmailConfig(
        enabled=True,
        consent_granted=True,
        imap_host="imap.example.com",
        imap_port=993,
        imap_username="bot@example.com",
        imap_password="secret",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="bot@example.com",
        smtp_password="secret",
        mark_seen=True,
    )


def _make_raw_email(
    from_addr: str = "alice@example.com",
    subject: str = "Hello",
    body: str = "This is the body.",
) -> bytes:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = "bot@example.com"
    msg["Subject"] = subject
    msg["Message-ID"] = "<m1@example.com>"
    msg.set_content(body)
    return msg.as_bytes()


__all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]
