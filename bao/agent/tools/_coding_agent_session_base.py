from __future__ import annotations

import shlex
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

from loguru import logger

from bao.agent.tools._coding_agent_cache import RunResult
from bao.agent.tools._coding_agent_runtime import run_command
from bao.agent.tools.coding_session_store import CodingSessionEvent


class CodingAgentSessionMixin:
    async def _resolve_stored_session_id(self, context_key: str) -> str | None:
        if self._session_store is None:
            return None
        try:
            maybe = await self._session_store.load(
                context_key=context_key,
                backend=self.session_backend,
            )
        except Exception as exc:
            logger.debug("{} session lookup failed: {}", self._tool_label, exc)
            return None
        return maybe.strip() if isinstance(maybe, str) and maybe.strip() else None

    async def _publish_session_event(
        self,
        *,
        context_key: str,
        session_id: str | None,
        action: Literal["active", "cleared"],
        reason: str | None = None,
    ) -> None:
        if self._session_store is None:
            return
        event = CodingSessionEvent(
            backend=self.session_backend,
            context_key=context_key,
            session_id=session_id.strip() if isinstance(session_id, str) and session_id.strip() else None,
            action=action,
            reason=reason,
        )
        try:
            await self._session_store.publish(event)
        except Exception as exc:
            logger.debug("{} session event failed: {}", self._tool_label, exc)

    def _parse_execute_options(
        self, kwargs: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        prompt = kwargs.get("prompt")
        if not isinstance(prompt, str):
            return None, "Error: prompt must be a string"
        prompt_text = prompt.strip()
        if not prompt_text:
            return None, "Error: prompt cannot be empty"

        project_path = kwargs.get("project_path")
        if project_path is not None and not isinstance(project_path, str):
            return None, "Error: project_path must be a string"

        session_id = kwargs.get("session_id")
        if session_id is not None and not isinstance(session_id, str):
            return None, "Error: session_id must be a string"

        continue_session = kwargs.get("continue_session", True)
        if not isinstance(continue_session, bool):
            return None, "Error: continue_session must be a boolean"

        model = kwargs.get("model")
        if model is not None and not isinstance(model, str):
            return None, "Error: model must be a string"

        timeout_raw = kwargs.get("timeout_seconds")
        if timeout_raw is not None and not isinstance(timeout_raw, int):
            return None, "Error: timeout_seconds must be an integer"

        response_format = kwargs.get("response_format", "hybrid")
        if response_format not in ("hybrid", "json", "text"):
            return None, "Error: response_format must be one of: hybrid, json, text"

        max_retries = kwargs.get("max_retries", 1)
        if not isinstance(max_retries, int):
            return None, "Error: max_retries must be an integer"

        max_output_raw = kwargs.get("max_output_chars", 4000)
        if not isinstance(max_output_raw, int):
            return None, "Error: max_output_chars must be an integer"

        include_details = kwargs.get("include_details", False)
        if not isinstance(include_details, bool):
            return None, "Error: include_details must be a boolean"

        return {
            "prompt_text": prompt_text,
            "project_path": project_path,
            "session_id": session_id,
            "continue_session": continue_session,
            "model": model,
            "timeout_raw": timeout_raw,
            "response_format": response_format,
            "max_retries": max(0, min(max_retries, 2)),
            "max_output_chars": max(200, min(max_output_raw, 50000)),
            "include_details": include_details,
            "extra_params": kwargs,
        }, None

    async def _resolve_session_for_execute(
        self,
        *,
        explicit_session_id: str | None,
        continue_session: bool,
        context_key: str,
    ) -> tuple[str | None, str]:
        resolved_session = explicit_session_id
        source = "explicit" if resolved_session else "none"
        if not resolved_session and continue_session:
            resolved_session = await self._resolve_stored_session_id(context_key)
            if resolved_session:
                source = "stored"
        return resolved_session, source

    async def _run_command_once(
        self,
        *,
        cmd: list[str],
        cwd: Path,
        timeout: int,
    ) -> tuple[RunResult, int, int]:
        start = time.monotonic()
        attempts = 1
        try:
            result = await self._run_command(
                cmd=cmd,
                cwd=cwd,
                timeout_seconds=timeout,
                on_stdout_line=self._progress_callback,
            )
        except TypeError as exc:
            if "on_stdout_line" not in str(exc):
                raise
            result = await self._run_command(
                cmd=cmd,
                cwd=cwd,
                timeout_seconds=timeout,
            )
        duration_ms = int((time.monotonic() - start) * 1000)
        return result, attempts, duration_ms

    def _resolve_project_path(self, project_path: str | None) -> Path:
        try:
            target = Path(project_path).expanduser().resolve() if project_path else self.workspace
        except Exception:
            raise ValueError(f"Invalid project_path: {project_path!r}") from None
        if not target.exists() or not target.is_dir():
            raise ValueError(f"project_path does not exist or is not a directory: {target}")
        if self.allowed_dir and self.allowed_dir not in target.parents and target != self.allowed_dir:
            raise ValueError("project_path is outside the allowed workspace")
        return target

    @staticmethod
    def _build_command_preview(cmd: list[str], prompt_text: str) -> str:
        compact_prompt = prompt_text.strip().replace("\n", " ")
        if len(compact_prompt) > 160:
            compact_prompt = compact_prompt[:160] + "..."
        if not cmd:
            return ""
        preview_parts = [shlex.quote(part) for part in cmd[:-1]]
        preview_parts.append(shlex.quote(compact_prompt))
        return " ".join(preview_parts)

    @staticmethod
    async def _run_command(
        cmd: list[str],
        cwd: Path,
        timeout_seconds: int,
        on_stdout_line: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> RunResult:
        return await run_command(
            cmd=cmd,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            on_stdout_line=on_stdout_line,
        )
