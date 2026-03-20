from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bao.agent.tool_result import ToolResultValue


@dataclass(slots=True)
class WriteArtifactFileRequest:
    kind: str
    name_hint: str
    source_path: Path
    size: int
    move_source: bool = True
    redacted: bool | None = None


@dataclass(slots=True)
class ToolOutputBudgetRequest:
    store: Any | None
    tool_name: str
    tool_call_id: str
    result: ToolResultValue
    offload_chars: int = 8000
    preview_chars: int = 3000
    hard_chars: int = 6000
    ctx_mgmt: str = "auto"


@dataclass(slots=True)
class ToolOutputBudgetEvent:
    offloaded: bool = False
    offloaded_chars: int = 0
    hard_clipped: bool = False
    hard_clipped_chars: int = 0
