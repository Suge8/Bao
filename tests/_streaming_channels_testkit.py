# ruff: noqa: F401
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


class _DiscordResponse:
    def __init__(self, data: dict[str, object], status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return self._data

    def raise_for_status(self) -> None:
        return None


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


__all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]
