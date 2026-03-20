# ruff: noqa: F401
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import websockets
from pydantic import SecretStr

from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels.base import BaseChannel
from bao.channels.discord import DiscordChannel
from bao.channels.email import EmailChannel
from bao.channels.imessage import IMessageChannel
from bao.channels.mochat import MochatChannel
from bao.channels.whatsapp import WhatsAppChannel
from bao.config.schema import (
    DiscordConfig,
    EmailConfig,
    IMessageConfig,
    MochatConfig,
    WhatsAppConfig,
)


class _DummyChannel(BaseChannel):
    name = "dummy"

    def __init__(self) -> None:
        super().__init__(IMessageConfig(enabled=True), MessageBus())

    async def start(self) -> None:
        self._start_lifecycle()

    async def stop(self) -> None:
        self._stop_lifecycle()

    async def send(self, msg: OutboundMessage) -> None:
        _ = msg


class _FakeAsyncWs:
    def __init__(self) -> None:
        self.closed = asyncio.Event()
        self.sent: list[str] = []

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    async def close(self) -> None:
        self.closed.set()

    def __aiter__(self) -> _FakeAsyncWs:
        return self

    async def __anext__(self) -> str:
        await self.closed.wait()
        raise StopAsyncIteration


class _AsyncWsContext:
    def __init__(self, ws: _FakeAsyncWs) -> None:
        self._ws = ws

    async def __aenter__(self) -> _FakeAsyncWs:
        return self._ws

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def _email_config() -> EmailConfig:
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
    )


def _new_mochat_channel() -> MochatChannel:
    return MochatChannel(
        MochatConfig(enabled=True, claw_token=SecretStr("tok")),
        MagicMock(),
    )


def _install_waiting_mochat_workers(channel: MochatChannel, gate: asyncio.Event) -> None:
    async def _wait_for_gate(_target_id: str) -> None:
        await gate.wait()

    channel._session_watch_worker = _wait_for_gate  # type: ignore[method-assign]
    channel._panel_poll_worker = _wait_for_gate  # type: ignore[method-assign]


__all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]
