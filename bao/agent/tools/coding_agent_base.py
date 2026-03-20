"""Shared base for CLI-based coding agent tools (OpenCode, Codex, etc.)."""

from __future__ import annotations

import shutil
from abc import ABC
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from bao.agent.tools._coding_agent_cache import (
    MIN_TOOL_TIMEOUT_SECONDS as _MIN_TOOL_TIMEOUT_SECONDS,
)
from bao.agent.tools._coding_agent_cache import DetailCache
from bao.agent.tools._coding_agent_details_base import (
    BaseCodingDetailsTool as _BaseCodingDetailsTool,
)
from bao.agent.tools._coding_agent_execute_base import CodingAgentExecuteMixin
from bao.agent.tools._coding_agent_health import (
    CodingBackendHealth,
    get_cached_backend_health,
    set_cached_backend_health,
)
from bao.agent.tools._coding_agent_response_base import CodingAgentResponseMixin
from bao.agent.tools._coding_agent_session_base import CodingAgentSessionMixin
from bao.agent.tools.base import Tool
from bao.agent.tools.coding_session_store import CodingSessionStore

__all__ = [
    "BaseCodingAgentTool",
    "BaseCodingDetailsTool",
    "DetailCache",
    "shutil",
]


class BaseCodingAgentTool(
    CodingAgentExecuteMixin,
    CodingAgentResponseMixin,
    CodingAgentSessionMixin,
    Tool,
    ABC,
):
    """Abstract base for tools that wrap an external coding CLI."""

    _TRANSIENT_MARKERS: tuple[str, ...] = (
        "timeout",
        "timed out",
        "temporar",
        "rate limit",
        "429",
        "econnreset",
        "eai_again",
    )
    _STALE_SESSION_MARKERS: tuple[str, ...] = (
        "no conversation found",
        "session not found",
        "unknown session",
        "invalid session",
        "could not find session",
        "no such session",
    )

    def __init__(
        self,
        workspace: Path,
        allowed_dir: Path | None = None,
        default_timeout_seconds: int = 1800,
        *,
        detail_cache: DetailCache | None = None,
        session_store: CodingSessionStore | None = None,
    ):
        self.workspace: Path = Path(workspace).resolve()
        self.allowed_dir: Path | None = Path(allowed_dir).resolve() if allowed_dir else None
        self.default_timeout_seconds: int = max(
            _MIN_TOOL_TIMEOUT_SECONDS,
            int(default_timeout_seconds),
        )
        self._channel: ContextVar[str] = ContextVar("coding_channel", default="hub")
        self._chat_id: ContextVar[str] = ContextVar("coding_chat_id", default="direct")
        self._context_key: ContextVar[str] = ContextVar(
            "coding_context_key",
            default="hub:direct",
        )
        self.detail_cache: DetailCache = detail_cache or DetailCache()
        self._progress_callback: Callable[[str], Awaitable[None] | None] | None = None
        self._session_store = session_store

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        self._channel.set(channel)
        self._chat_id.set(chat_id)
        self._context_key.set(session_key or f"{channel}:{chat_id}")

    def set_progress_callback(
        self,
        callback: Callable[[str], Awaitable[None] | None] | None,
    ) -> None:
        self._progress_callback = callback

    @property
    def session_backend(self) -> str:
        return self.name

    @property
    def cli_binary(self) -> str:
        raise NotImplementedError

    @property
    def _tool_label(self) -> str:
        raise NotImplementedError

    @property
    def _meta_prefix(self) -> str:
        raise NotImplementedError

    def _validate_extra_params(self, kwargs: dict[str, Any]) -> str | None:
        return None

    async def _prepare_extra_params(
        self,
        *,
        cwd: Path,
        timeout: int,
        extra_params: dict[str, Any],
    ) -> dict[str, Any]:
        del cwd, timeout
        return extra_params

    def _build_command(
        self,
        *,
        prompt: str,
        resolved_session: str | None,
        model: str | None,
        context_key: str,
        extra_params: dict[str, Any],
    ) -> tuple[list[str], dict[str, Any]]:
        raise NotImplementedError

    async def _extract_output(self, *, stdout_text: str, exec_state: dict[str, Any]) -> str:
        return stdout_text.strip() or "(no output)"

    async def _resolve_session_after_success(
        self,
        *,
        stdout_text: str,
        resolved_session: str | None,
        cwd: Path,
        exec_state: dict[str, Any],
        timeout: int,
    ) -> str | None:
        del stdout_text, cwd, exec_state, timeout
        return resolved_session

    def _cleanup(self, exec_state: dict[str, Any]) -> None:
        del exec_state

    def _error_type_impl(self, stdout_text: str, stderr_text: str) -> str:
        del stdout_text, stderr_text
        return "execution_failed"

    def _classify_error_type(self, stdout_text: str, stderr_text: str) -> str:
        if self._is_stale_session_error(stdout_text, stderr_text):
            return "stale_session"
        return self._error_type_impl(stdout_text, stderr_text)

    def _build_failure_hints(self, stdout_text: str, stderr_text: str) -> list[str]:
        del stdout_text, stderr_text
        return []

    def _extra_payload_fields(self, extra_params: dict[str, Any]) -> dict[str, Any]:
        del extra_params
        return {}

    def _extra_meta_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        del payload
        return {}

    def _detail_stdout_for_cache(
        self,
        *,
        final_output: str,
        stdout_text: str,
        exec_state: dict[str, Any],
    ) -> str:
        del stdout_text, exec_state
        return final_output

    def _is_transient_failure(self, stdout_text: str, stderr_text: str) -> bool:
        lowered = f"{stdout_text}\n{stderr_text}".lower()
        return any(marker in lowered for marker in self._TRANSIENT_MARKERS)

    def _is_stale_session_error(self, stdout_text: str, stderr_text: str) -> bool:
        lowered = f"{stdout_text}\n{stderr_text}".lower()
        return any(marker in lowered for marker in self._STALE_SESSION_MARKERS)

    async def probe_health(self, timeout_seconds: int = 20) -> CodingBackendHealth:
        cached = get_cached_backend_health(self.name, str(self.workspace))
        if cached is not None:
            return cached
        if not shutil.which(self.cli_binary):
            return set_cached_backend_health(
                self.name,
                str(self.workspace),
                CodingBackendHealth(
                    backend=self.name,
                    ready=False,
                    error_type="missing_binary",
                    message=f"{self.cli_binary} not found on PATH.",
                ),
            )
        result = await self._probe_backend_health(timeout_seconds=max(5, int(timeout_seconds)))
        return set_cached_backend_health(self.name, str(self.workspace), result)

    async def _probe_backend_health(self, timeout_seconds: int) -> CodingBackendHealth:
        del timeout_seconds
        return CodingBackendHealth(backend=self.name, ready=True)


BaseCodingDetailsTool = _BaseCodingDetailsTool
