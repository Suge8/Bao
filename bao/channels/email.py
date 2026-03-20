"""Email channel implementation using IMAP polling + SMTP replies."""

from __future__ import annotations

import imaplib
import smtplib

from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.config.schema import EmailConfig

from ._email_common import _EmailCommonMixin
from ._email_fetch import _EmailFetchMixin
from ._email_lifecycle import _EmailLifecycleMixin
from ._email_outbound import _EmailOutboundMixin

__all__ = ["EmailChannel", "imaplib", "smtplib"]


class EmailChannel(
    _EmailLifecycleMixin,
    _EmailOutboundMixin,
    _EmailFetchMixin,
    _EmailCommonMixin,
    BaseChannel,
):
    """Email channel."""

    name = "email"
    def __init__(self, config: EmailConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: EmailConfig = config
        self._last_subject_by_chat: dict[str, str] = {}
        self._last_message_id_by_chat: dict[str, str] = {}
        self._processed_uids: set[str] = set()  # Capped to prevent unbounded growth
        self._MAX_PROCESSED_UIDS = 100000
