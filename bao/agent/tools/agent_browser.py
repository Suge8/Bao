from __future__ import annotations

import asyncio
import os
import re
import shutil
from contextvars import ContextVar
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bao.agent.tools.base import Tool

_ACTION_ALIASES = {"scroll_into_view": "scrollintoview"}
_ACTION_ENUM = (
    "open",
    "click",
    "dblclick",
    "type",
    "fill",
    "press",
    "hover",
    "focus",
    "check",
    "uncheck",
    "select",
    "drag",
    "upload",
    "download",
    "scroll",
    "scroll_into_view",
    "wait",
    "screenshot",
    "pdf",
    "snapshot",
    "eval",
    "connect",
    "close",
    "back",
    "forward",
    "reload",
    "get",
    "is",
    "find",
    "mouse",
    "set",
    "network",
    "cookies",
    "storage",
    "tab",
    "diff",
    "trace",
    "profiler",
    "record",
    "console",
    "errors",
    "highlight",
    "session",
    "install",
)
_PATH_ARG_ACTIONS: dict[str, tuple[int, ...]] = {
    "upload": (1,),
    "download": (1,),
    "screenshot": (0,),
    "pdf": (0,),
    "record": (1,),
}
_LOCAL_PATH_RE = re.compile(r"^(?:[A-Za-z]:\\|/|~(?:/|$)|\.\.?/)")


def agent_browser_available() -> bool:
    return bool(shutil.which("agent-browser"))


class AgentBrowserRunner:
    def __init__(
        self,
        *,
        workspace: Path,
        allowed_dir: Path | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self.workspace = workspace
        self.allowed_dir = allowed_dir
        self.timeout_seconds = max(5, int(timeout_seconds))
        self._context_session: ContextVar[str] = ContextVar(
            "agent_browser_session",
            default="default",
        )

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        base = (
            session_key
            if isinstance(session_key, str) and session_key.strip()
            else f"{channel}:{chat_id}"
        )
        self._context_session.set(self.normalize_session(base))

    @staticmethod
    def normalize_session(value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
        normalized = normalized.strip("-._")
        return (normalized or "default")[:80]

    async def run(self, *, action: str, args: list[str] | None = None, **options: Any) -> str:
        binary = shutil.which("agent-browser")
        if not binary:
            return "Error: agent-browser CLI is not installed or not on PATH"

        if action not in _ACTION_ENUM:
            return "Error: action must be one of the supported agent_browser commands"

        normalized_args = args or []
        if not isinstance(normalized_args, list) or not all(
            isinstance(arg, str) for arg in normalized_args
        ):
            return "Error: args must be an array of strings"

        path_error = self._validate_paths(action=action, args=normalized_args, options=options)
        if path_error:
            return path_error

        command = self._build_command(binary, action=action, args=normalized_args, options=options)
        return await self._run_command(command)

    async def fetch_html(
        self, url: str, *, wait_ms: int = 1500, session: str | None = None
    ) -> dict[str, str]:
        open_error = await self._run_fetch_step("open", [url], session=session)
        if open_error is not None:
            return {"error": open_error}

        wait_error = await self._run_fetch_step("wait", [str(max(wait_ms, 0))], session=session)
        if wait_error is not None:
            return {"error": wait_error}

        html_result = await self.run(
            action="get",
            args=["html", "body"],
            session=session,
            json_output=False,
        )
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
        if result.startswith("Error:"):
            return result
        return None

    def _build_command(
        self,
        binary: str,
        *,
        action: str,
        args: list[str],
        options: dict[str, Any],
    ) -> list[str]:
        cmd = [binary]

        session_value = options.get("session")
        if isinstance(session_value, str) and session_value.strip():
            session_name = self.normalize_session(session_value)
        else:
            session_name = self._context_session.get()
        if session_name:
            cmd.extend(["--session", session_name])

        for key, flag in (
            ("profile_path", "--profile"),
            ("state_path", "--state"),
            ("config_path", "--config"),
            ("executable_path", "--executable-path"),
            ("headers_json", "--headers"),
            ("user_agent", "--user-agent"),
            ("proxy", "--proxy"),
            ("provider", "--provider"),
            ("device", "--device"),
            ("cdp", "--cdp"),
            ("session_name", "--session-name"),
        ):
            value = options.get(key)
            if isinstance(value, str) and value.strip():
                cmd.extend([flag, value.strip()])

        if options.get("headed"):
            cmd.append("--headed")
        if options.get("json_output", True):
            cmd.append("--json")
        if options.get("full_page"):
            cmd.append("--full")
        if options.get("annotate"):
            cmd.append("--annotate")
        if options.get("ignore_https_errors"):
            cmd.append("--ignore-https-errors")
        if options.get("allow_file_access"):
            cmd.append("--allow-file-access")
        if options.get("auto_connect"):
            cmd.append("--auto-connect")

        cmd.append(_ACTION_ALIASES.get(action, action))
        cmd.extend(args)
        return cmd

    def _validate_paths(
        self, *, action: str, args: list[str], options: dict[str, Any]
    ) -> str | None:
        if self.allowed_dir is None:
            return None

        for key in ("profile_path", "state_path", "config_path", "executable_path"):
            value = options.get(key)
            if isinstance(value, str) and value.strip():
                err = self._validate_single_path(value.strip())
                if err:
                    return f"Error: {key} {err}"

        for index in _PATH_ARG_ACTIONS.get(action, ()):
            if index >= len(args):
                continue
            target = args[index].strip()
            if not target:
                continue
            err = self._validate_single_path(target)
            if err:
                return f"Error: path argument {err}"
        return None

    def _validate_single_path(self, raw: str) -> str | None:
        if self.allowed_dir is None:
            return None
        value = urlparse(raw).path if raw.startswith("file://") else raw
        if not self._looks_like_path(value):
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.workspace / path
        resolved = path.resolve(strict=False)
        allowed = self.allowed_dir.resolve(strict=False)
        if resolved != allowed and allowed not in resolved.parents:
            return "must stay within the workspace"
        return None

    @staticmethod
    def _looks_like_path(value: str) -> bool:
        return bool(_LOCAL_PATH_RE.match(value))

    async def _run_command(self, command: list[str]) -> str:
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),
                env=os.environ.copy(),
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self.timeout_seconds
                )
            except asyncio.TimeoutError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                return f"Error: agent-browser timed out after {self.timeout_seconds} seconds"
        except asyncio.CancelledError:
            if process and process.returncode is None:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
            raise
        except Exception as exc:
            return f"Error: agent-browser execution failed: {exc}"

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if process.returncode == 0:
            return stdout_text or stderr_text or "(no output)"

        detail = stderr_text or stdout_text or "unknown error"
        return f"Error: {detail} (exit code: {process.returncode})"


class AgentBrowserTool(Tool):
    def __init__(
        self,
        *,
        workspace: Path,
        allowed_dir: Path | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self._runner = AgentBrowserRunner(
            workspace=workspace,
            allowed_dir=allowed_dir,
            timeout_seconds=timeout_seconds,
        )

    @property
    def available(self) -> bool:
        return agent_browser_available()

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        self._runner.set_context(channel, chat_id, session_key)

    @property
    def name(self) -> str:
        return "agent_browser"

    @property
    def description(self) -> str:
        return "Control a real browser through the agent-browser CLI for interactive pages, forms, screenshots, and DOM inspection."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": list(_ACTION_ENUM)},
                "args": {"type": "array", "items": {"type": "string"}},
                "session": {"type": "string"},
                "session_name": {"type": "string"},
                "profile_path": {"type": "string"},
                "state_path": {"type": "string"},
                "config_path": {"type": "string"},
                "executable_path": {"type": "string"},
                "headers_json": {"type": "string"},
                "user_agent": {"type": "string"},
                "proxy": {"type": "string"},
                "provider": {"type": "string"},
                "device": {"type": "string"},
                "cdp": {"type": "string"},
                "headed": {"type": "boolean"},
                "json_output": {"type": "boolean"},
                "full_page": {"type": "boolean"},
                "annotate": {"type": "boolean"},
                "ignore_https_errors": {"type": "boolean"},
                "allow_file_access": {"type": "boolean"},
                "auto_connect": {"type": "boolean"},
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        args = kwargs.get("args")
        other = {k: v for k, v in kwargs.items() if k not in {"action", "args"}}
        if not isinstance(action, str):
            return "Error: Missing required parameter 'action'"
        return await self._runner.run(
            action=action, args=args if isinstance(args, list) else [], **other
        )
