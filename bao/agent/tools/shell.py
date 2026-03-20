"""Shell execution tool."""

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bao.agent.tool_result import ToolResultValue, ToolTextResult
from bao.agent.tools._shell_guard import (
    DEFAULT_DENY_PATTERNS,
    READ_ONLY_ALLOW_PATTERNS,
    READ_ONLY_BLOCK_PATTERNS,
)
from bao.agent.tools._shell_io import (
    await_pending_tasks,
    cleanup_temp_path,
    compose_result_file,
    drain_stream_to_file,
    make_temp_path,
    read_inline_result,
)
from bao.agent.tools.base import Tool

logger = logging.getLogger(__name__)


@dataclass
class ShellRunContext:
    process: asyncio.subprocess.Process
    stdout_path: Path
    stderr_path: Path
    stdout_task: asyncio.Task[int]
    stderr_task: asyncio.Task[int]


@dataclass(frozen=True, slots=True)
class ExecToolOptions:
    timeout: int = 60
    working_dir: str | None = None
    deny_patterns: tuple[str, ...] | None = None
    allow_patterns: tuple[str, ...] | None = None
    restrict_to_workspace: bool = False
    path_append: str = ""
    sandbox_mode: str = "semi-auto"


class ExecTool(Tool):
    """Tool to execute shell commands."""

    def __init__(self, options: ExecToolOptions | None = None):
        resolved_options = options or ExecToolOptions()
        self.timeout = resolved_options.timeout
        self.working_dir = resolved_options.working_dir
        self.path_append = resolved_options.path_append
        self.sandbox_mode = resolved_options.sandbox_mode

        if resolved_options.sandbox_mode == "full-auto":
            self.deny_patterns = []
            self.allow_patterns = []
            self.restrict_to_workspace = False
            return

        self.deny_patterns = list(resolved_options.deny_patterns or DEFAULT_DENY_PATTERNS)
        if resolved_options.sandbox_mode == "read-only":
            self.allow_patterns = list(READ_ONLY_ALLOW_PATTERNS)
            self.restrict_to_workspace = True
            return

        if resolved_options.sandbox_mode != "semi-auto":
            logger.warning(
                "⚠️ 沙箱模式未知 / unknown mode: {!r}, falling back to semi-auto",
                resolved_options.sandbox_mode,
            )
        self.allow_patterns = list(resolved_options.allow_patterns or ())
        self.restrict_to_workspace = resolved_options.restrict_to_workspace

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return "Execute a shell command and return its output. Use with caution."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute"},
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory for the command",
                },
            },
            "required": ["command"],
        }

    async def execute(self, **kwargs: Any) -> ToolResultValue:
        command = kwargs.get("command")
        working_dir = kwargs.get("working_dir")
        if not isinstance(command, str) or not command:
            return "Error: command is required"
        if working_dir is not None and not isinstance(working_dir, str):
            return "Error: working_dir must be a string"
        cwd = working_dir or self.working_dir or os.getcwd()
        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return guard_error
        return await self._run_command(command, cwd)

    async def _run_command(self, command: str, cwd: str) -> ToolResultValue:
        combined_result: ToolTextResult | None = None
        context: ShellRunContext | None = None

        try:
            context = await self._start_process(command, cwd)
            result = await self._collect_process_result(context)
            if isinstance(result, str):
                return result
            combined_result = result
            inline_text = read_inline_result(combined_result)
            if inline_text is not None:
                combined_result = None
                return inline_text
            return combined_result

        except asyncio.CancelledError:
            await self._cancel_process(context)
            raise
        except Exception as e:
            if context is not None:
                await await_pending_tasks(context.stdout_task, context.stderr_task)
            return f"Error executing command: {str(e)}"
        finally:
            if combined_result is None and context is not None:
                cleanup_temp_path(context.stdout_path)
                cleanup_temp_path(context.stderr_path)

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.path_append.strip():
            parts = [env.get("PATH", ""), self.path_append.strip()]
            env["PATH"] = os.pathsep.join(p for p in parts if p)
        return env

    async def _start_process(self, command: str, cwd: str) -> ShellRunContext:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=self._build_env(),
        )
        stdout_path = make_temp_path("bao_exec_stdout_")
        stderr_path = make_temp_path("bao_exec_stderr_")
        return ShellRunContext(
            process=process,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            stdout_task=asyncio.create_task(drain_stream_to_file(process.stdout, stdout_path)),
            stderr_task=asyncio.create_task(drain_stream_to_file(process.stderr, stderr_path)),
        )

    async def _collect_process_result(self, context: ShellRunContext) -> ToolTextResult | str:
        try:
            await asyncio.wait_for(context.process.wait(), timeout=self.timeout)
            stdout_chars, stderr_chars = await asyncio.gather(
                context.stdout_task,
                context.stderr_task,
            )
        except asyncio.TimeoutError:
            context.process.kill()
            try:
                await asyncio.wait_for(context.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
            await asyncio.gather(
                context.stdout_task,
                context.stderr_task,
                return_exceptions=True,
            )
            return f"Error: Command timed out after {self.timeout} seconds"
        return await asyncio.to_thread(
            compose_result_file,
            context.stdout_path,
            context.stderr_path,
            stdout_chars=stdout_chars,
            stderr_chars=stderr_chars,
            return_code=context.process.returncode or 0,
        )

    async def _cancel_process(self, context: ShellRunContext | None) -> None:
        if context is None:
            return
        if context.process.returncode is None:
            context.process.kill()
            try:
                await asyncio.wait_for(context.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass
        await await_pending_tasks(context.stdout_task, context.stderr_task)

    def _guard_command(self, command: str, cwd: str) -> str | None:
        """Best-effort safety guard for potentially destructive commands."""
        cmd = command.strip()
        lower = cmd.lower()

        for pattern in self.deny_patterns:
            if re.search(pattern, lower):
                return "Error: Command blocked by safety guard (dangerous pattern detected)"

        if self.allow_patterns:
            if not any(re.search(p, lower) for p in self.allow_patterns):
                return "Error: Command blocked by safety guard (not in allowlist)"

        if self.sandbox_mode == "read-only":
            for pattern in READ_ONLY_BLOCK_PATTERNS:
                if re.search(pattern, lower):
                    return "Error: Command blocked by read-only sandbox"

        if self.restrict_to_workspace:
            if "..\\" in cmd or "../" in cmd:
                return "Error: Command blocked by safety guard (path traversal detected)"

            cwd_path = Path(cwd).resolve()

            for raw in self._extract_absolute_paths(cmd):
                try:
                    p = Path(raw.strip()).resolve()
                except Exception:
                    continue
                if p.is_absolute() and cwd_path not in p.parents and p != cwd_path:
                    return "Error: Command blocked by safety guard (path outside working dir)"

        return None

    @staticmethod
    def _extract_absolute_paths(command: str) -> list[str]:
        win_quoted_double = re.findall(r'"([A-Za-z]:\\[^"]+)"', command)
        win_quoted_single = re.findall(r"'([A-Za-z]:\\[^']+)'", command)
        win_unquoted = re.findall(r"[A-Za-z]:\\[^\s\"'|><;]+", command)

        posix_quoted_double = re.findall(r'"(/[^\"]+)"', command)
        posix_quoted_single = re.findall(r"'(/[^']+)'", command)
        posix_unquoted = re.findall(r"(?:^|[\s|>])(/[^\s\"'>]+)", command)

        ordered = (
            win_quoted_double
            + win_quoted_single
            + win_unquoted
            + posix_quoted_double
            + posix_quoted_single
            + posix_unquoted
        )
        deduped: list[str] = []
        seen: set[str] = set()
        for path in ordered:
            if path in seen:
                continue
            seen.add(path)
            deduped.append(path)
        return deduped
