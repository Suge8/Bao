"""Shell execution tool."""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any

from bao.agent.tools.base import Tool

logger = logging.getLogger(__name__)


class ExecTool(Tool):
    """Tool to execute shell commands."""

    _READ_ONLY_ALLOW_PATTERNS: list[str] = [
        r"^\s*(cat|ls|find|grep|head|tail|wc|file|stat|echo|pwd|which|env|printenv|less|more|tree|du|diff|basename|dirname|realpath)\b",
    ]

    _READ_ONLY_BLOCK_PATTERNS: list[str] = [
        r"(?:^|[^\\])(>>?|1>|2>|&>)",
        r"\|\s*tee\b",
        r"\b(touch|mkdir|cp|mv|install|ln|truncate)\b",
        r"\b(python|python3|node|ruby|perl|php|lua)\b",
        r"\b(vi|vim|nano|emacs)\b",
    ]

    _DEFAULT_DENY_PATTERNS: list[str] = [
        r"\brm\s+-[rf]{1,2}\b",  # rm -r, rm -rf, rm -fr
        r"\bdel\s+/[fq]\b",  # del /f, del /q
        r"\brmdir\s+/s\b",  # rmdir /s
        r"(?:^|[;&|]\s*)format\b",  # format (as standalone command only)
        r"\b(mkfs|diskpart)\b",  # disk operations
        r"\bdd\s+if=",  # dd
        r">\s*/dev/sd",  # write to disk
        r"\b(shutdown|reboot|poweroff)\b",  # system power
        r":\(\)\s*\{.*\};\s*:",  # fork bomb
    ]

    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
        path_append: str = "",
        sandbox_mode: str = "semi-auto",
    ):
        self.timeout = timeout
        self.working_dir = working_dir
        self.path_append = path_append
        self.sandbox_mode = sandbox_mode

        if sandbox_mode == "full-auto":
            self.deny_patterns: list[str] = []
            self.allow_patterns: list[str] = []
            self.restrict_to_workspace = False
        elif sandbox_mode == "read-only":
            self.deny_patterns = deny_patterns or list(self._DEFAULT_DENY_PATTERNS)
            self.allow_patterns = list(self._READ_ONLY_ALLOW_PATTERNS)
            self.restrict_to_workspace = True
        else:
            if sandbox_mode != "semi-auto":
                logger.warning(
                    "⚠️ 沙箱模式未知 / unknown mode: {!r}, falling back to semi-auto",
                    sandbox_mode,
                )
            self.deny_patterns = deny_patterns or list(self._DEFAULT_DENY_PATTERNS)
            self.allow_patterns = allow_patterns or []
            self.restrict_to_workspace = restrict_to_workspace

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

    async def execute(self, **kwargs: Any) -> str:
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

        env = os.environ.copy()
        if self.path_append.strip():
            parts = [env.get("PATH", ""), self.path_append.strip()]
            env["PATH"] = os.pathsep.join(p for p in parts if p)

        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
            except asyncio.TimeoutError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                return f"Error: Command timed out after {self.timeout} seconds"

            output_parts = []

            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))

            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")

            if process.returncode != 0:
                output_parts.append(f"\nExit code: {process.returncode}")

            result = "\n".join(output_parts) if output_parts else "(no output)"
            max_len = 10000
            if len(result) > max_len:
                result = result[:max_len] + f"\n... (truncated, {len(result) - max_len} more chars)"

            return result

        except asyncio.CancelledError:
            if process and process.returncode is None:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
            raise
        except Exception as e:
            return f"Error executing command: {str(e)}"

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
            for pattern in self._READ_ONLY_BLOCK_PATTERNS:
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
