from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RuntimeEventRequest:
    source: str
    stage: str
    message: str
    level: str = "error"
    code: str = ""
    retryable: bool | None = None
    session_key: str = ""
    details: dict[str, Any] = field(default_factory=dict)
