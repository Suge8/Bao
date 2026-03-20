from __future__ import annotations

import asyncio
import re
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from ._runtime_common import ACTION_ALIASES, PATH_ARG_ACTIONS, SUPPORTED_ACTION_SET, looks_like_path
from ._runtime_state import (
    BrowserCapabilityState,
    build_runtime_environment,
    get_browser_capability_state,
    resolve_profile_dir,
)


@dataclass(frozen=True)
class BrowserAutomationOptions:
    enabled: bool = True
    allowed_dir: Path | None = None
    timeout_seconds: int = 120


@dataclass(frozen=True)
class BrowserCommandRequest:
    action: str
    args: list[str]
    options: dict[str, Any]
    profile_path: Path


class BrowserAutomationService:
    def __init__(
        self,
        workspace: Path,
        options: BrowserAutomationOptions | None = None,
    ) -> None:
        runtime_options = options or BrowserAutomationOptions()
        self.workspace = workspace
        self.allowed_dir = runtime_options.allowed_dir
        self.timeout_seconds = max(5, int(runtime_options.timeout_seconds))
        self._enabled = runtime_options.enabled
        self._context_session: ContextVar[str] = ContextVar(
            "browser_automation_session",
            default="default",
        )

    @property
    def state(self) -> BrowserCapabilityState:
        return get_browser_capability_state(enabled=self._enabled)

    @property
    def available(self) -> bool:
        return self.state.available

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        base = session_key if isinstance(session_key, str) and session_key.strip() else f"{channel}:{chat_id}"
        self._context_session.set(self.normalize_session(base))

    @staticmethod
    def normalize_session(value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
        normalized = normalized.strip("-._")
        return (normalized or "default")[:80]

    @staticmethod
    def supports_action(action: str) -> bool:
        return action in SUPPORTED_ACTION_SET

    async def run(self, *, action: str, args: list[str] | None = None, **options: Any) -> str:
        state = self.state
        if not state.enabled:
            return "Error: browser automation is disabled by config"
        if not state.available:
            return f"Error: managed browser runtime is not ready: {state.detail}"
        if action not in SUPPORTED_ACTION_SET:
            return "Error: action must be one of the supported browser automation commands"
        normalized_args = args or []
        if not isinstance(normalized_args, list) or not all(isinstance(arg, str) for arg in normalized_args):
            return "Error: args must be an array of strings"
        path_error = self._validate_paths(action=action, args=normalized_args)
        if path_error:
            return path_error
        command = self._build_command(
            state,
            BrowserCommandRequest(
                action=action,
                args=normalized_args,
                options=options,
                profile_path=resolve_profile_dir(create=True),
            ),
        )
        return await self._run_command(command, env=build_runtime_environment(state))

    async def smoke_test(self) -> str | None:
        state = self.state
        if not state.available:
            return f"Error: managed browser runtime is not ready: {state.detail}"
        session = self.normalize_session(f"runtime-smoke-{uuid4().hex[:12]}")
        open_result = await self.run(action="open", args=["about:blank"], session=session, json_output=False)
        if open_result.startswith("Error:"):
            return open_result
        result: str | None = None
        url_result = await self.run(action="get", args=["url"], session=session, json_output=False)
        if url_result.startswith("Error:"):
            result = url_result
        elif url_result.strip() != "about:blank":
            result = f"Error: browser smoke test returned unexpected URL: {url_result.strip() or '(empty)'}"
        close_result = await self.run(action="close", args=[], session=session, json_output=False)
        if close_result.startswith("Error:"):
            return close_result
        return result

    async def fetch_html(
        self, url: str, *, wait_ms: int = 1500, session: str | None = None
    ) -> dict[str, str]:
        open_error = await self._run_fetch_step("open", [url], session=session)
        if open_error is not None:
            return {"error": open_error}
        wait_error = await self._run_fetch_step("wait", [str(max(wait_ms, 0))], session=session)
        if wait_error is not None:
            return {"error": wait_error}
        html_result = await self.run(action="get", args=["html", "body"], session=session, json_output=False)
        if html_result.startswith("Error:"):
            return {"error": html_result}
        final_url = await self.run(action="get", args=["url"], session=session, json_output=False)
        if final_url.startswith("Error:"):
            final_url = url
        return {"html": html_result, "final_url": final_url.strip() or url}

    async def _run_fetch_step(
        self, action: str, args: list[str], *, session: str | None = None
    ) -> str | None:
        result = await self.run(action=action, args=args, session=session, json_output=False)
        return result if result.startswith("Error:") else None

    def _build_command(
        self,
        state: BrowserCapabilityState,
        request: BrowserCommandRequest,
    ) -> list[str]:
        command = [
            state.agent_browser_path,
            "--profile",
            str(request.profile_path),
            "--executable-path",
            state.browser_executable_path,
        ]
        self._append_session_flag(command, request.options)
        self._append_string_flags(command, request.options)
        self._append_boolean_flags(command, request.options)
        command.append(ACTION_ALIASES.get(request.action, request.action))
        command.extend(request.args)
        return command

    def _append_session_flag(self, command: list[str], options: dict[str, Any]) -> None:
        session_value = options.get("session")
        if isinstance(session_value, str) and session_value.strip():
            session_name = self.normalize_session(session_value)
        else:
            session_name = self._context_session.get()
        if session_name:
            command.extend(["--session", session_name])

    @staticmethod
    def _append_string_flags(command: list[str], options: dict[str, Any]) -> None:
        for key, flag in (("headers_json", "--headers"), ("user_agent", "--user-agent"), ("proxy", "--proxy")):
            value = options.get(key)
            if isinstance(value, str) and value.strip():
                command.extend([flag, value.strip()])

    @staticmethod
    def _append_boolean_flags(command: list[str], options: dict[str, Any]) -> None:
        for key, flag in (
            ("headed", "--headed"),
            ("full_page", "--full"),
            ("annotate", "--annotate"),
            ("ignore_https_errors", "--ignore-https-errors"),
            ("allow_file_access", "--allow-file-access"),
        ):
            if options.get(key):
                command.append(flag)
        if options.get("json_output", True):
            command.append("--json")

    def _validate_paths(self, *, action: str, args: list[str]) -> str | None:
        if self.allowed_dir is None:
            return None
        for index in PATH_ARG_ACTIONS.get(action, ()):
            if index >= len(args):
                continue
            target = args[index].strip()
            if not target:
                continue
            error = self._validate_single_path(target)
            if error:
                return f"Error: path argument {error}"
        return None

    def _validate_single_path(self, raw: str) -> str | None:
        if self.allowed_dir is None:
            return None
        value = urlparse(raw).path if raw.startswith("file://") else raw
        if not looks_like_path(value):
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.workspace / path
        resolved = path.resolve(strict=False)
        allowed = self.allowed_dir.resolve(strict=False)
        if resolved != allowed and allowed not in resolved.parents:
            return "must stay within the workspace"
        return None

    async def _run_command(self, command: list[str], *, env: dict[str, str]) -> str:
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
                env=env,
            )
            stdout, stderr, timeout_error = await self._communicate_with_timeout(process)
        except asyncio.CancelledError:
            await self._kill_process(process)
            raise
        except Exception as exc:
            return f"Error: agent-browser execution failed: {exc}"
        if timeout_error is not None:
            return timeout_error
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if process.returncode == 0:
            return stdout_text or stderr_text or "(no output)"
        detail = stderr_text or stdout_text or "unknown error"
        return f"Error: {detail} (exit code: {process.returncode})"

    async def _communicate_with_timeout(
        self, process: asyncio.subprocess.Process
    ) -> tuple[bytes, bytes, str | None]:
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
            return stdout, stderr, None
        except asyncio.TimeoutError:
            await self._kill_process(process)
            return b"", b"", f"Error: agent-browser timed out after {self.timeout_seconds} seconds"

    @staticmethod
    async def _kill_process(process: asyncio.subprocess.Process | None) -> None:
        if process is None or process.returncode is not None:
            return
        process.kill()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            return
