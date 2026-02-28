"""Shared base for CLI-based coding agent tools (OpenCode, Codex, etc.)."""

import asyncio
import codecs
import inspect
import json
import os
import shlex
import shutil
import signal
import time
import uuid
from abc import ABC
from collections import deque
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from pathlib import Path
from typing import Any, TypedDict

from loguru import logger

from bao.agent.tools.base import Tool

# ---------------------------------------------------------------------------
# Detail cache — per-instance, shared between a CodingAgentTool and its
# companion DetailsTool via the same DetailCache reference.
# ---------------------------------------------------------------------------

_DETAIL_CACHE_LIMIT = 128
_DETAIL_CACHE_TEXT_MAX = 120_000


class _DetailRecord(TypedDict):
    request_id: str
    context_key: str
    session_id: str | None
    project_path: str
    status: str
    command_preview: str
    stdout: str
    stderr: str
    summary: str
    attempts: int
    duration_ms: int
    exit_code: int | None
    created_at: int
    cache_truncated: bool


class _RunResult(TypedDict):
    timed_out: bool
    returncode: int | None
    stdout: str
    stderr: str


class DetailCache:
    """LRU detail cache shared between a coding-agent tool and its details tool."""

    def __init__(self, limit: int = _DETAIL_CACHE_LIMIT, text_max: int = _DETAIL_CACHE_TEXT_MAX):
        self._limit = limit
        self._text_max = text_max
        self._cache: dict[str, _DetailRecord] = {}
        self._order: deque[str] = deque()
        self._last_by_context: dict[str, str] = {}
        self._last_by_session: dict[str, str] = {}

    # -- helpers --

    def _trim_text(self, text: str) -> tuple[str, bool]:
        if len(text) <= self._text_max:
            return text, False
        omitted = len(text) - self._text_max
        return text[: self._text_max] + f"\n... (detail cache truncated {omitted} chars)", True

    # -- public API --

    def store(self, record: _DetailRecord) -> None:
        rid = record["request_id"]
        self._cache[rid] = record
        self._order.append(rid)
        self._last_by_context[record["context_key"]] = rid
        if record["session_id"]:
            self._last_by_session[record["session_id"]] = rid

        while len(self._order) > self._limit:
            old = self._order.popleft()
            rec = self._cache.pop(old, None)
            if not rec:
                continue
            if self._last_by_context.get(rec["context_key"]) == old:
                self._last_by_context.pop(rec["context_key"], None)
            sid = rec.get("session_id")
            if sid and self._last_by_session.get(sid) == old:
                self._last_by_session.pop(sid, None)

    def lookup(
        self, *, request_id: str | None, session_id: str | None, context_key: str
    ) -> _DetailRecord | None:
        if request_id:
            rec = self._cache.get(request_id)
            if rec and rec.get("context_key") == context_key:
                return rec
            return None
        if session_id:
            rid = self._last_by_session.get(session_id)
            if rid:
                rec = self._cache.get(rid)
                if rec and rec.get("context_key") == context_key:
                    return rec
            return None
        latest = self._last_by_context.get(context_key)
        if latest:
            return self._cache.get(latest)
        return None

    def build_detail_record(
        self,
        *,
        request_id: str,
        context_key: str,
        session_id: str | None,
        project_path: str,
        status: str,
        command_preview: str,
        stdout: str,
        stderr: str,
        summary: str,
        attempts: int,
        duration_ms: int,
        exit_code: int | None,
    ) -> None:
        clipped_stdout, stdout_trunc = self._trim_text(stdout)
        clipped_stderr, stderr_trunc = self._trim_text(stderr)
        self.store(
            {
                "request_id": request_id,
                "context_key": context_key,
                "session_id": session_id,
                "project_path": project_path,
                "status": status,
                "command_preview": command_preview,
                "stdout": clipped_stdout,
                "stderr": clipped_stderr,
                "summary": summary,
                "attempts": attempts,
                "duration_ms": duration_ms,
                "exit_code": exit_code,
                "created_at": int(time.time()),
                "cache_truncated": stdout_trunc or stderr_trunc,
            }
        )


# ---------------------------------------------------------------------------
# BaseCodingAgentTool — template-method base for CLI coding agents
# ---------------------------------------------------------------------------


class BaseCodingAgentTool(Tool, ABC):
    """Abstract base for tools that wrap an external coding CLI."""

    def __init__(
        self,
        workspace: Path,
        allowed_dir: Path | None = None,
        default_timeout_seconds: int = 600,
        *,
        detail_cache: DetailCache | None = None,
    ):
        self.workspace: Path = Path(workspace).resolve()
        self.allowed_dir: Path | None = Path(allowed_dir).resolve() if allowed_dir else None
        self.default_timeout_seconds: int = max(30, int(default_timeout_seconds))
        self._channel: ContextVar[str] = ContextVar("coding_channel", default="gateway")
        self._chat_id: ContextVar[str] = ContextVar("coding_chat_id", default="direct")
        self._context_key: ContextVar[str] = ContextVar(
            "coding_context_key", default="gateway:direct"
        )
        self._session_by_context: dict[str, str] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self.detail_cache: DetailCache = detail_cache or DetailCache()
        self._progress_callback: Callable[[str], Awaitable[None] | None] | None = None

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        self._channel.set(channel)
        self._chat_id.set(chat_id)
        self._context_key.set(session_key or f"{channel}:{chat_id}")

    def set_progress_callback(
        self, callback: Callable[[str], Awaitable[None] | None] | None
    ) -> None:
        self._progress_callback = callback

    # -- abstract properties (subclass MUST override) --

    @property
    def cli_binary(self) -> str:
        """CLI executable name, e.g. 'opencode' or 'codex'."""
        raise NotImplementedError

    @property
    def _tool_label(self) -> str:
        """Human-readable label, e.g. 'OpenCode' or 'Codex'."""
        raise NotImplementedError

    @property
    def _meta_prefix(self) -> str:
        """Hybrid-format meta key, e.g. 'OPENCODE_META' or 'CODEX_META'."""
        raise NotImplementedError

    # -- abstract methods (subclass MUST override) --

    def _validate_extra_params(self, kwargs: dict[str, Any]) -> str | None:
        """Validate tool-specific params. Return error string or None."""
        return None

    def _build_command(
        self,
        *,
        prompt: str,
        resolved_session: str | None,
        model: str | None,
        context_key: str,
        extra_params: dict[str, Any],
    ) -> tuple[list[str], dict[str, Any]]:
        """Build CLI command. Return (cmd_list, exec_state)."""
        raise NotImplementedError

    async def _extract_output(self, *, stdout_text: str, exec_state: dict[str, Any]) -> str:
        """Extract final output from run result. Default: use stdout."""
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
        """Resolve session id after successful run. Default: return resolved_session."""
        return resolved_session

    def _cleanup(self, exec_state: dict[str, Any]) -> None:
        """Clean up resources created during execution (e.g. temp files)."""

    def _error_type_impl(self, stdout_text: str, stderr_text: str) -> str:
        """Classify error type from output."""
        return "execution_failed"

    def _build_failure_hints(self, stdout_text: str, stderr_text: str) -> list[str]:
        """Build actionable hints for failure output."""
        return []

    def _extra_payload_fields(self, extra_params: dict[str, Any]) -> dict[str, Any]:
        """Return extra fields to include in payload (e.g. {'agent': ...})."""
        return {}

    def _extra_meta_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return extra fields to include in hybrid meta dict."""
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

    # -- transient failure detection (overridable) --

    _TRANSIENT_MARKERS: tuple[str, ...] = (
        "timeout",
        "timed out",
        "temporar",
        "rate limit",
        "429",
        "econnreset",
        "eai_again",
    )

    def _is_transient_failure(self, stdout_text: str, stderr_text: str) -> bool:
        lowered = f"{stdout_text}\n{stderr_text}".lower()
        return any(m in lowered for m in self._TRANSIENT_MARKERS)

    _STALE_SESSION_MARKERS: tuple[str, ...] = (
        "no conversation found",
        "session not found",
        "unknown session",
        "invalid session",
        "could not find session",
        "no such session",
    )

    def _is_stale_session_error(self, stdout_text: str, stderr_text: str) -> bool:
        lowered = f"{stdout_text}\n{stderr_text}".lower()
        return any(m in lowered for m in self._STALE_SESSION_MARKERS)

    # -- main execute (template method) --

    async def execute(self, **kwargs: Any) -> str:
        _session_retry = kwargs.pop("__session_retry", False)
        _original_kwargs = dict(kwargs)
        # 1. Common param validation
        prompt = kwargs.get("prompt")
        if not isinstance(prompt, str):
            return "Error: prompt must be a string"
        prompt_text = prompt.strip()
        if not prompt_text:
            return "Error: prompt cannot be empty"

        project_path = kwargs.get("project_path")
        if project_path is not None and not isinstance(project_path, str):
            return "Error: project_path must be a string"

        session_id = kwargs.get("session_id")
        if session_id is not None and not isinstance(session_id, str):
            return "Error: session_id must be a string"

        continue_session = kwargs.get("continue_session", True)
        if not isinstance(continue_session, bool):
            return "Error: continue_session must be a boolean"

        model = kwargs.get("model")
        if model is not None and not isinstance(model, str):
            return "Error: model must be a string"

        timeout_raw = kwargs.get("timeout_seconds")
        if timeout_raw is not None and not isinstance(timeout_raw, int):
            return "Error: timeout_seconds must be an integer"

        response_format = kwargs.get("response_format", "hybrid")
        if response_format not in ("hybrid", "json", "text"):
            return "Error: response_format must be one of: hybrid, json, text"

        max_retries = kwargs.get("max_retries", 1)
        if not isinstance(max_retries, int):
            return "Error: max_retries must be an integer"
        max_retries = max(0, min(max_retries, 2))

        max_output_raw = kwargs.get("max_output_chars", 4000)
        if not isinstance(max_output_raw, int):
            return "Error: max_output_chars must be an integer"
        max_output_chars = max(200, min(max_output_raw, 50000))

        include_details = kwargs.get("include_details", False)
        if not isinstance(include_details, bool):
            return "Error: include_details must be a boolean"

        # 2. Subclass-specific param validation
        extra_err = self._validate_extra_params(kwargs)
        if extra_err:
            return extra_err

        request_id = uuid.uuid4().hex
        context_key = self._context_key.get()
        timeout = max(30, min(int(timeout_raw or self.default_timeout_seconds), 1800))
        extra_params = kwargs  # subclass reads its own extras from here

        # 3. Binary check
        if not shutil.which(self.cli_binary):
            return self._error_response(
                status="error",
                message=(
                    f"Error: `{self.cli_binary}` command not found. "
                    f"Install {self._tool_label} first and ensure it is on PATH."
                ),
                project_path=str(self.workspace),
                timeout_seconds=timeout,
                used_session_id=None,
                continued=False,
                model=model,
                attempts=0,
                duration_ms=0,
                exit_code=None,
                summary=f"{self._tool_label} CLI is not installed or not in PATH.",
                error_type="missing_binary",
                request_id=request_id,
                context_key=context_key,
                command_preview="",
                response_format=response_format,
                extra_params=extra_params,
            )

        # 4. Resolve project path
        try:
            cwd = self._resolve_project_path(project_path)
        except ValueError as e:
            return self._error_response(
                status="error",
                message=f"Error: {e}",
                project_path=str(project_path or self.workspace),
                timeout_seconds=timeout,
                used_session_id=None,
                continued=False,
                model=model,
                attempts=0,
                duration_ms=0,
                exit_code=None,
                summary=f"Invalid project path: {project_path or self.workspace}",
                error_type="invalid_project_path",
                request_id=request_id,
                context_key=context_key,
                command_preview="",
                response_format=response_format,
                extra_params=extra_params,
            )

        # 5. Resolve session
        resolved_session = session_id
        if not resolved_session and continue_session:
            async with self._lock:
                resolved_session = self._session_by_context.get(context_key)

        session_from_cache = bool(resolved_session and not session_id)

        # 6. Build command (subclass hook) — inside try/finally so _cleanup
        #    runs even if _build_command_preview raises after _build_command
        #    already created resources (e.g. Codex temp file).
        exec_state: dict[str, Any] = {}
        try:
            cmd, exec_state = self._build_command(
                prompt=prompt_text,
                resolved_session=resolved_session,
                model=model,
                context_key=context_key,
                extra_params=extra_params,
            )
            command_preview = self._build_command_preview(cmd, prompt_text)

            # 7. Retry loop
            attempts = 0
            start = time.monotonic()
            result: _RunResult | None = None
            while attempts <= max_retries:
                attempts += 1
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
                if result["timed_out"]:
                    break
                if result["returncode"] == 0:
                    break
                if attempts > max_retries:
                    break
                if not self._is_transient_failure(result["stdout"], result["stderr"]):
                    break

            if result is None:
                result = {"timed_out": True, "returncode": None, "stdout": "", "stderr": ""}

            duration_ms = int((time.monotonic() - start) * 1000)

            # 8. Timeout
            if result["timed_out"]:
                return self._error_response(
                    status="timeout",
                    message=(
                        f"Error: {self._tool_label} timed out after {timeout} seconds. "
                        "Try narrowing the task, or increase timeout_seconds."
                    ),
                    project_path=str(cwd),
                    timeout_seconds=timeout,
                    used_session_id=resolved_session,
                    continued=bool(resolved_session),
                    model=model,
                    attempts=attempts,
                    duration_ms=duration_ms,
                    exit_code=None,
                    summary=f"{self._tool_label} timed out after {timeout} seconds.",
                    error_type="timeout",
                    request_id=request_id,
                    context_key=context_key,
                    command_preview=command_preview,
                    response_format=response_format,
                    extra_params=extra_params,
                    hints=["Split the task into smaller steps or raise timeout_seconds."],
                )

            stdout_text = result["stdout"]
            stderr_text = result["stderr"]
            return_code = result["returncode"]
            exec_state["_returncode"] = return_code
            # 9. Extract output (subclass hook)
            final_output = await self._extract_output(
                stdout_text=stdout_text, exec_state=exec_state
            )
            detail_stdout = self._detail_stdout_for_cache(
                final_output=final_output,
                stdout_text=stdout_text,
                exec_state=exec_state,
            )

            # 10. Failure
            if return_code is None or return_code != 0:
                # Stale session auto-recovery: clear cache and retry once
                if (
                    not _session_retry
                    and session_from_cache
                    and self._is_stale_session_error(stdout_text, stderr_text)
                ):
                    async with self._lock:
                        self._session_by_context.pop(context_key, None)
                    logger.debug(
                        "{}: stale session {}, retrying fresh",
                        self._tool_label,
                        resolved_session,
                    )
                    return await self.execute(**_original_kwargs, __session_retry=True)
                return self._failure_response(
                    return_code=int(return_code or -1),
                    final_output=final_output,
                    stdout_text=stdout_text,
                    stderr_text=stderr_text,
                    project_path=str(cwd),
                    timeout_seconds=timeout,
                    used_session_id=resolved_session,
                    continued=bool(resolved_session),
                    model=model,
                    attempts=attempts,
                    duration_ms=duration_ms,
                    max_output_chars=max_output_chars,
                    include_details=include_details,
                    request_id=request_id,
                    context_key=context_key,
                    command_preview=command_preview,
                    response_format=response_format,
                    extra_params=extra_params,
                    stdout_for_cache=detail_stdout,
                )

            # 11. Success — resolve session (subclass hook)
            active_session = await self._resolve_session_after_success(
                stdout_text=stdout_text,
                resolved_session=resolved_session,
                cwd=cwd,
                exec_state=exec_state,
                timeout=timeout,
            )

            if active_session:
                async with self._lock:
                    self._session_by_context[context_key] = active_session

            body = final_output.strip() or "(no output)"
            if len(body) > max_output_chars:
                body = body[:max_output_chars] + (
                    f"\n... (truncated, {len(body) - max_output_chars} more chars)"
                )
            stderr_clean = stderr_text.strip()
            summary = self._summarize_output(body, stderr_clean)
            details_available = bool(body or stderr_clean)
            details_hint = self._build_details_hint(
                request_id=request_id,
                session_id=active_session,
                include_details=include_details,
                details_available=details_available,
            )

            header = f"{self._tool_label} completed successfully."
            if active_session:
                header += f"\nSession: {active_session}"

            extras = self._extra_payload_fields(extra_params)
            payload: dict[str, Any] = {
                "schema_version": 1,
                "request_id": request_id,
                "status": "success",
                "message": header,
                "project_path": str(cwd),
                "timeout_seconds": timeout,
                "session_id": active_session,
                "continued": bool(resolved_session),
                "model": model,
                **extras,
                "attempts": attempts,
                "duration_ms": duration_ms,
                "exit_code": 0,
                "stdout": body if include_details else "",
                "stderr": stderr_clean if include_details else "",
                "summary": summary,
                "details_available": details_available,
                "details_hint": details_hint,
                "hints": [],
                "error_type": None,
                "command_preview": command_preview,
            }
            self.detail_cache.build_detail_record(
                request_id=request_id,
                context_key=context_key,
                session_id=active_session,
                project_path=str(cwd),
                status="success",
                command_preview=command_preview,
                stdout=detail_stdout,
                stderr=stderr_text,
                summary=summary,
                attempts=attempts,
                duration_ms=duration_ms,
                exit_code=0,
            )
            return self._render_payload(payload, response_format=response_format)
        finally:
            self._cleanup(exec_state)

    # -- internal helpers --

    def _error_response(
        self,
        *,
        status: str,
        message: str,
        project_path: str,
        timeout_seconds: int,
        used_session_id: str | None,
        continued: bool,
        model: str | None,
        attempts: int,
        duration_ms: int,
        exit_code: int | None,
        summary: str,
        error_type: str,
        request_id: str,
        context_key: str,
        command_preview: str,
        response_format: str,
        extra_params: dict[str, Any],
        hints: list[str] | None = None,
    ) -> str:
        extras = self._extra_payload_fields(extra_params)
        payload: dict[str, Any] = {
            "schema_version": 1,
            "request_id": request_id,
            "status": status,
            "message": message,
            "project_path": project_path,
            "timeout_seconds": timeout_seconds,
            "session_id": used_session_id,
            "continued": continued,
            "model": model,
            **extras,
            "attempts": attempts,
            "duration_ms": duration_ms,
            "exit_code": exit_code,
            "stdout": "",
            "stderr": "",
            "summary": summary,
            "details_available": False,
            "details_hint": None,
            "hints": hints or [],
            "error_type": error_type,
            "command_preview": command_preview,
        }
        self.detail_cache.build_detail_record(
            request_id=request_id,
            context_key=context_key,
            session_id=used_session_id,
            project_path=project_path,
            status=status,
            command_preview=command_preview,
            stdout="",
            stderr="",
            summary=summary,
            attempts=attempts,
            duration_ms=duration_ms,
            exit_code=exit_code,
        )
        return self._render_payload(payload, response_format=response_format)

    def _failure_response(
        self,
        *,
        return_code: int,
        final_output: str,
        stdout_text: str,
        stderr_text: str,
        project_path: str,
        timeout_seconds: int,
        used_session_id: str | None,
        continued: bool,
        model: str | None,
        attempts: int,
        duration_ms: int,
        max_output_chars: int,
        include_details: bool,
        request_id: str,
        context_key: str,
        command_preview: str,
        response_format: str,
        extra_params: dict[str, Any],
        stdout_for_cache: str,
    ) -> str:
        out = stdout_text.strip()
        err = stderr_text.strip()
        hints = self._build_failure_hints(out, err)
        if not hints and self._is_transient_failure(out, err):
            hints.append(
                "Transient failure detected; retry the same task or increase timeout_seconds."
            )
        summary = self._summarize_output(final_output, err)
        details_available = bool(final_output or err)
        details_hint = self._build_details_hint(
            request_id=request_id,
            session_id=used_session_id,
            include_details=include_details,
            details_available=details_available,
        )
        extras = self._extra_payload_fields(extra_params)
        payload: dict[str, Any] = {
            "schema_version": 1,
            "request_id": request_id,
            "status": "error",
            "message": f"Error: {self._tool_label} failed (exit code {return_code}).",
            "project_path": project_path,
            "timeout_seconds": timeout_seconds,
            "session_id": used_session_id,
            "continued": continued,
            "model": model,
            **extras,
            "attempts": attempts,
            "duration_ms": duration_ms,
            "exit_code": return_code,
            "stdout": final_output[:max_output_chars] if include_details else "",
            "stderr": err[:max_output_chars] if include_details else "",
            "summary": summary,
            "details_available": details_available,
            "details_hint": details_hint,
            "hints": hints,
            "error_type": self._error_type_impl(out, err),
            "command_preview": command_preview,
        }
        self.detail_cache.build_detail_record(
            request_id=request_id,
            context_key=context_key,
            session_id=used_session_id,
            project_path=project_path,
            status="error",
            command_preview=command_preview,
            stdout=stdout_for_cache,
            stderr=stderr_text,
            summary=summary,
            attempts=attempts,
            duration_ms=duration_ms,
            exit_code=return_code,
        )
        return self._render_payload(payload, response_format=response_format)

    def _resolve_project_path(self, project_path: str | None) -> Path:
        try:
            target = Path(project_path).expanduser().resolve() if project_path else self.workspace
        except Exception:
            raise ValueError(f"Invalid project_path: {project_path!r}") from None
        if not target.exists() or not target.is_dir():
            raise ValueError(f"project_path does not exist or is not a directory: {target}")
        if (
            self.allowed_dir
            and self.allowed_dir not in target.parents
            and target != self.allowed_dir
        ):
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
    ) -> _RunResult:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
            start_new_session=True,
        )

        async def _read_stream(
            stream: asyncio.StreamReader | None,
            buf: list[str],
            *,
            on_line: Callable[[str], Awaitable[None] | None] | None = None,
        ) -> str:
            if stream is None:
                return ""
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            remainder = ""
            while True:
                chunk = await stream.read(8192)
                if not chunk:
                    tail = decoder.decode(b"", final=True)
                    if tail:
                        buf.append(tail)
                        remainder += tail
                    if remainder and remainder.strip() and on_line:
                        await _fire_cb(on_line, remainder.strip())
                    break
                text = decoder.decode(chunk)
                buf.append(text)
                if on_line is None:
                    continue
                parts = (remainder + text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
                remainder = parts[-1]
                for part in parts[:-1]:
                    cleaned = part.strip()
                    if cleaned:
                        await _fire_cb(on_line, cleaned)
            return "".join(buf)

        async def _fire_cb(
            cb: Callable[[str], Awaitable[None] | None], text: str
        ) -> None:
            try:
                maybe = cb(text)
                if inspect.isawaitable(maybe):
                    await maybe
            except Exception as exc:
                logger.debug("coding tool progress callback failed: {}", exc)

        async def _graceful_kill() -> None:
            """SIGTERM → 2 s grace → SIGKILL."""
            if process.returncode is not None:
                return
            # Stage 1: SIGTERM
            try:
                if hasattr(os, "killpg"):
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
            except ProcessLookupError:
                return
            except Exception:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
                return
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            # Stage 2: SIGKILL
            if process.returncode is not None:
                return
            try:
                if hasattr(os, "killpg"):
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            except Exception:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=3.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        stdout_buf: list[str] = []
        stderr_buf: list[str] = []
        stdout_task: asyncio.Task[str] | None = None
        stderr_task: asyncio.Task[str] | None = None

        async def _drain_tasks() -> None:
            pending = [t for t in (stdout_task, stderr_task) if t and not t.done()]
            if pending:
                done, still = await asyncio.wait(pending, timeout=0.5)
                for task in still:
                    task.cancel()
            if stdout_task or stderr_task:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(
                            *(t for t in (stdout_task, stderr_task) if t),
                            return_exceptions=True,
                        ),
                        timeout=2.0,
                    )
                except asyncio.TimeoutError:
                    pass

        try:
            stdout_task = asyncio.create_task(
                _read_stream(process.stdout, stdout_buf, on_line=on_stdout_line)
            )
            stderr_task = asyncio.create_task(_read_stream(process.stderr, stderr_buf))
            await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
            stdout = await stdout_task
            stderr = await stderr_task
            return {
                "timed_out": False,
                "returncode": int(process.returncode or 0),
                "stdout": stdout,
                "stderr": stderr,
            }
        except asyncio.TimeoutError:
            await _graceful_kill()
            await _drain_tasks()
            return {
                "timed_out": True,
                "returncode": None,
                "stdout": "".join(stdout_buf),
                "stderr": "".join(stderr_buf),
            }
        except asyncio.CancelledError:
            await _graceful_kill()
            await _drain_tasks()
            raise

    @staticmethod
    def _summarize_output(stdout_text: str, stderr_text: str, max_chars: int = 1600) -> str:
        main = BaseCodingAgentTool._trim_for_summary(stdout_text.strip(), max_chars=max_chars)
        if stderr_text:
            err = BaseCodingAgentTool._trim_for_summary(stderr_text.strip(), max_chars=500)
            if main and main != "(no output)":
                return f"{main}\n\n[stderr]\n{err}"
            return f"[stderr]\n{err}"
        return main

    @staticmethod
    def _trim_for_summary(text: str, max_chars: int) -> str:
        if not text:
            return "(no output)"
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        head = text[:half].rstrip()
        tail = text[-half:].lstrip()
        return f"{head}\n...\n{tail}"

    def _build_details_hint(
        self,
        request_id: str,
        session_id: str | None,
        include_details: bool,
        details_available: bool,
    ) -> str | None:
        if include_details or not details_available:
            return None
        tool_name = self.name
        details_tool = f"{tool_name}_details"
        if session_id:
            return (
                "Detailed output omitted to protect context budget. "
                f"Use {details_tool} with request_id '{request_id}', "
                f"or resume session '{session_id}'."
            )
        return (
            "Detailed output omitted to protect context budget. "
            f"Use {details_tool} with request_id '{request_id}' to view full stdout/stderr."
        )

    def _render_payload(self, payload: dict[str, Any], response_format: str) -> str:
        if response_format == "json":
            return json.dumps(payload, ensure_ascii=False)

        if response_format == "text":
            parts = [payload["message"]]
            if payload["session_id"]:
                parts.append(f"Session: {payload['session_id']}")
            if payload["summary"]:
                parts.append(f"Summary:\n{payload['summary']}")
            if payload["stdout"]:
                parts.append(payload["stdout"])
            if payload["stderr"]:
                parts.append(f"STDERR:\n{payload['stderr']}")
            if payload["details_hint"]:
                parts.append(f"Details:\n{payload['details_hint']}")
            if payload["hints"]:
                parts.append("Hints:\n- " + "\n- ".join(payload["hints"]))
            return "\n\n".join(parts)

        # hybrid (default)
        meta: dict[str, Any] = {
            "schema_version": payload["schema_version"],
            "request_id": payload["request_id"],
            "status": payload["status"],
            "error_type": payload["error_type"],
            "session_id": payload["session_id"],
            "continued": payload["continued"],
            "project_path": payload["project_path"],
            "timeout_seconds": payload["timeout_seconds"],
            "duration_ms": payload["duration_ms"],
            "attempts": payload["attempts"],
            "exit_code": payload["exit_code"],
            **self._extra_meta_fields(payload),
            "model": payload["model"],
            "command_preview": payload["command_preview"],
            "details_available": payload["details_available"],
        }
        lines = [payload["message"], f"{self._meta_prefix}=" + json.dumps(meta, ensure_ascii=False)]
        if payload["summary"]:
            lines.extend(["Summary:", payload["summary"]])
        if payload["stdout"]:
            lines.extend(["Output:", payload["stdout"]])
        if payload["stderr"]:
            lines.extend(["STDERR:", payload["stderr"]])
        if payload["details_hint"]:
            lines.extend(["Details:", payload["details_hint"]])
        if payload["hints"]:
            lines.extend(["Hints:", "- " + "\n- ".join(payload["hints"])])
        return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# BaseCodingDetailsTool — companion details-fetch tool
# ---------------------------------------------------------------------------


class BaseCodingDetailsTool(Tool, ABC):
    """Abstract base for the *_details companion tool."""

    def __init__(self, *, detail_cache: DetailCache, default_max_chars: int = 12000):
        self.detail_cache = detail_cache
        self.default_max_chars = max(200, int(default_max_chars))
        self._channel: ContextVar[str] = ContextVar("coding_details_channel", default="gateway")
        self._chat_id: ContextVar[str] = ContextVar("coding_details_chat_id", default="direct")
        self._context_key: ContextVar[str] = ContextVar(
            "coding_details_context_key", default="gateway:direct"
        )

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        self._channel.set(channel)
        self._chat_id.set(chat_id)
        self._context_key.set(session_key or f"{channel}:{chat_id}")

    # -- abstract properties (subclass MUST override) --

    @property
    def _tool_label(self) -> str:
        raise NotImplementedError

    @property
    def _meta_prefix(self) -> str:
        """e.g. 'OPENCODE_DETAIL_META' or 'CODEX_DETAIL_META'."""
        raise NotImplementedError

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "request_id": {
                    "type": "string",
                    "description": f"Preferred: request_id from {self._meta_prefix.replace('_DETAIL', '')}",
                },
                "session_id": {
                    "type": "string",
                    "description": f"Fallback: {self._tool_label} session id",
                },
                "max_chars": {
                    "type": "integer",
                    "minimum": 200,
                    "maximum": 50000,
                    "description": "Max chars for stdout/stderr in response",
                },
                "include_stderr": {
                    "type": "boolean",
                    "description": "Whether to include stderr content",
                },
                "response_format": {
                    "type": "string",
                    "enum": ["hybrid", "json", "text"],
                    "description": "Return format: hybrid (default), json, or text",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> str:
        request_id = kwargs.get("request_id")
        if request_id is not None and not isinstance(request_id, str):
            return "Error: request_id must be a string"

        session_id = kwargs.get("session_id")
        if session_id is not None and not isinstance(session_id, str):
            return "Error: session_id must be a string"

        max_chars = kwargs.get("max_chars", self.default_max_chars)
        if not isinstance(max_chars, int):
            return "Error: max_chars must be an integer"
        max_chars = max(200, min(max_chars, 50000))

        include_stderr = kwargs.get("include_stderr", True)
        if not isinstance(include_stderr, bool):
            return "Error: include_stderr must be a boolean"

        response_format = kwargs.get("response_format", "hybrid")
        if response_format not in ("hybrid", "json", "text"):
            return "Error: response_format must be one of: hybrid, json, text"

        context_key = self._context_key.get()
        record = self.detail_cache.lookup(
            request_id=request_id, session_id=session_id, context_key=context_key
        )
        if not record:
            return (
                f"No {self._tool_label} detail record found. Provide request_id/session_id, "
                f"or run {self.name.replace('_details', '')} first in this chat context."
            )

        stdout = record["stdout"]
        if len(stdout) > max_chars:
            stdout = stdout[:max_chars] + f"\n... (truncated {len(stdout) - max_chars} chars)"

        stderr = record["stderr"] if include_stderr else ""
        if len(stderr) > max_chars:
            stderr = stderr[:max_chars] + f"\n... (truncated {len(stderr) - max_chars} chars)"

        payload = {
            "request_id": record["request_id"],
            "status": record["status"],
            "session_id": record["session_id"],
            "project_path": record["project_path"],
            "command_preview": record["command_preview"],
            "summary": record["summary"],
            "attempts": record["attempts"],
            "duration_ms": record["duration_ms"],
            "exit_code": record["exit_code"],
            "cache_truncated": record["cache_truncated"],
            "stdout": stdout,
            "stderr": stderr,
        }

        if response_format == "json":
            return json.dumps(payload, ensure_ascii=False)

        title = f"{self._tool_label} details: request_id={payload['request_id']} status={payload['status']}"
        parts: list[str] = [title, "Summary:", str(payload["summary"])]
        if response_format == "hybrid":
            parts.insert(1, f"{self._meta_prefix}=" + json.dumps(payload, ensure_ascii=False))
        if stdout:
            parts.extend(["Output:", stdout])
        if stderr:
            parts.extend(["STDERR:", stderr])
        return "\n\n".join(str(part) for part in parts)
