# ruff: noqa: F401
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import cast

import pytest

from bao.agent.loop import AgentLoop
from bao.bus.events import OutboundMessage
from bao.bus.queue import MessageBus
from bao.channels import imessage as imessage_module
from bao.channels.imessage import IMessageChannel
from bao.channels.progress_text import ProgressBuffer
from bao.config.schema import IMessageConfig
from bao.providers.base import ToolCallRequest

AUTOMATION_PERMISSION_HINT = cast(
    Callable[[str, str], str | None],
    getattr(imessage_module, "automation_permission_hint"),
)
PERMISSION_TARGET_LABEL = cast(
    Callable[[str], str],
    getattr(imessage_module, "permission_target_label"),
)


class _FakeProc:
    def __init__(self) -> None:
        self.returncode = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", b""


class _FailingProc:
    def __init__(self, stderr: bytes) -> None:
        self.returncode = 1
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"", self._stderr


__all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]
