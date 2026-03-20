from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine

if TYPE_CHECKING:
    from bao.providers.base import LLMProvider


@dataclass(slots=True)
class HeartbeatServiceOptions:
    workspace: Path
    provider: "LLMProvider"
    model: str
    on_execute: Callable[[str], Coroutine[Any, Any, str]] | None = None
    on_notify: Callable[[str], Coroutine[Any, Any, None]] | None = None
    interval_s: int = 30 * 60
    enabled: bool = True
    service_tier: str | None = None
