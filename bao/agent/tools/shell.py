"""Shell execution tool."""

import asyncio
import codecs
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from bao.agent.tool_result import (
    INLINE_TOOL_RESULT_CHARS,
    ToolResultValue,
    ToolTextResult,
    cleanup_result_file,
    make_file_preview,
)
from bao.agent.tools.base import Tool

logger = logging.getLogger(__name__)


class ExecTool(Tool):
    """Tool to execute shell commands."""

    _CHUNK_BYTES = 65536

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

        env = os.environ.copy()
        if self.path_append.strip():
            parts = [env.get("PATH", ""), self.path_append.strip()]
            env["PATH"] = os.pathsep.join(p for p in parts if p)

        process: asyncio.subprocess.Process | None = None
        stdout_path: Path | None = None
        stderr_path: Path | None = None
        combined_result: ToolTextResult | None = None
        stdout_task: asyncio.Task[int] | None = None
        stderr_task: asyncio.Task[int] | None = None
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
            stdout_path = self._make_temp_path("bao_exec_stdout_")
            stderr_path = self._make_temp_path("bao_exec_stderr_")
            stdout_task = asyncio.create_task(self._drain_stream_to_file(process.stdout, stdout_path))
            stderr_task = asyncio.create_task(self._drain_stream_to_file(process.stderr, stderr_path))
            try:
                await asyncio.wait_for(process.wait(), timeout=self.timeout)
                stdout_chars, stderr_chars = await asyncio.gather(stdout_task, stderr_task)
            except asyncio.TimeoutError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                return f"Error: Command timed out after {self.timeout} seconds"

            combined_result = await asyncio.to_thread(
                self._compose_result_file,
                stdout_path,
                stderr_path,
                stdout_chars=stdout_chars,
                stderr_chars=stderr_chars,
                return_code=process.returncode or 0,
            )
            inline_text = self._read_inline_result(combined_result)
            if inline_text is not None:
                combined_result = None
                return inline_text
            return combined_result

        except asyncio.CancelledError:
            if process and process.returncode is None:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
            await self._await_pending_tasks(stdout_task, stderr_task)
            raise
        except Exception as e:
            await self._await_pending_tasks(stdout_task, stderr_task)
            return f"Error executing command: {str(e)}"
        finally:
            if combined_result is None:
                self._cleanup_temp_path(stdout_path)
                self._cleanup_temp_path(stderr_path)

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

    @staticmethod
    def _make_temp_path(prefix: str) -> Path:
        fd, raw_path = tempfile.mkstemp(prefix=prefix, suffix=".txt")
        os.close(fd)
        return Path(raw_path)

    @staticmethod
    def _cleanup_temp_path(path: Path | None) -> None:
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    @staticmethod
    async def _await_pending_tasks(*tasks: asyncio.Task[int] | None) -> None:
        pending_tasks = [task for task in tasks if task is not None]
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)

    @staticmethod
    def _read_inline_result(result: ToolTextResult) -> str | None:
        if result.chars > INLINE_TOOL_RESULT_CHARS:
            return None
        text = result.path.read_text(encoding="utf-8", errors="replace")
        cleanup_result_file(result)
        return text or "(no output)"

    async def _drain_stream_to_file(
        self,
        stream: asyncio.StreamReader | None,
        path: Path,
    ) -> int:
        if stream is None:
            path.write_text("", encoding="utf-8")
            return 0
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        chars = 0
        with path.open("w", encoding="utf-8") as handle:
            while True:
                chunk = await stream.read(self._CHUNK_BYTES)
                if not chunk:
                    break
                text = decoder.decode(chunk)
                if not text:
                    continue
                handle.write(text)
                chars += len(text)
            tail = decoder.decode(b"", final=True)
            if tail:
                handle.write(tail)
                chars += len(tail)
        return chars

    def _compose_result_file(
        self,
        stdout_path: Path,
        stderr_path: Path,
        *,
        stdout_chars: int,
        stderr_chars: int,
        return_code: int,
    ) -> ToolTextResult:
        result_path = self._make_temp_path("bao_exec_result_")
        total_chars = 0
        with result_path.open("w", encoding="utf-8") as out_handle:
            total_chars += self._copy_text_file(stdout_path, out_handle)
            if stderr_chars > 0:
                prefix = "STDERR:\n"
                out_handle.write(prefix)
                total_chars += len(prefix)
                total_chars += self._copy_text_file(stderr_path, out_handle)
            if return_code != 0:
                exit_line = f"\nExit code: {return_code}"
                out_handle.write(exit_line)
                total_chars += len(exit_line)
        if total_chars == 0:
            result_path.write_text("(no output)", encoding="utf-8")
            total_chars = len("(no output)")
        excerpt = make_file_preview(result_path, min(2000, total_chars))
        return ToolTextResult(path=result_path, chars=total_chars, excerpt=excerpt, cleanup=True)

    @staticmethod
    def _copy_text_file(source_path: Path, out_handle: Any) -> int:
        chars = 0
        with source_path.open("r", encoding="utf-8", errors="replace") as in_handle:
            while True:
                chunk = in_handle.read(65536)
                if not chunk:
                    break
                out_handle.write(chunk)
                chars += len(chunk)
        return chars
