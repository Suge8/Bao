from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

SpawnResultStatus = Literal["spawned", "failed"]


@dataclass
class TaskStatus:
    task_id: str
    label: str
    task_description: str
    origin: dict[str, str]
    child_session_key: str | None = None
    status: str = "running"
    iteration: int = 0
    max_iterations: int = 20
    tool_steps: int = 0
    phase: str = "starting"
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    result_summary: str | None = None
    resume_context: str | None = None
    offloaded_count: int = 0
    offloaded_chars: int = 0
    clipped_count: int = 0
    clipped_chars: int = 0
    recent_actions: list[str] = field(default_factory=list)
    last_error_category: str | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None


@dataclass(frozen=True)
class SpawnIssue:
    code: str
    message: str

    def to_payload(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class SpawnTaskRef:
    task_id: str
    label: str
    status: str = "running"
    child_session_key: str | None = None

    def to_payload(self) -> dict[str, str]:
        payload = {
            "task_id": self.task_id,
            "label": self.label,
            "status": self.status,
        }
        if self.child_session_key:
            payload["child_session_key"] = self.child_session_key
        return payload


@dataclass(frozen=True)
class SpawnResult:
    status: SpawnResultStatus
    message: str
    task: SpawnTaskRef | None = None
    warning: SpawnIssue | None = None
    error: SpawnIssue | None = None
    schema_version: int = 1

    @classmethod
    def spawned(
        cls,
        *,
        task_id: str,
        label: str,
        child_session_key: str | None,
        warning: SpawnIssue | None = None,
    ) -> "SpawnResult":
        return cls(
            status="spawned",
            message=(
                "Subagent spawned. Query progress with task.task_id via check_tasks or "
                "check_tasks_json."
            ),
            task=SpawnTaskRef(
                task_id=task_id,
                label=label,
                child_session_key=child_session_key,
            ),
            warning=warning,
        )

    @classmethod
    def failed(cls, *, code: str, message: str) -> "SpawnResult":
        return cls(
            status="failed",
            message="Subagent spawn failed.",
            error=SpawnIssue(code=code, message=message),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "message": self.message,
            "task": self.task.to_payload() if self.task else None,
            "warning": self.warning.to_payload() if self.warning else None,
            "error": self.error.to_payload() if self.error else None,
        }
