from __future__ import annotations

import asyncio
import codecs
import inspect
from collections.abc import Awaitable, Callable
from pathlib import Path

from bao.agent.tools._coding_agent_cache import RunResult

_CHUNK_BYTES = 65536


async def _emit_line(
    line: str,
    callback: Callable[[str], Awaitable[None] | None] | None,
) -> None:
    if callback is None:
        return
    try:
        maybe = callback(line)
        if inspect.isawaitable(maybe):
            await maybe
    except Exception:
        return


async def _read_stream(
    stream: asyncio.StreamReader | None,
    *,
    callback: Callable[[str], Awaitable[None] | None] | None = None,
) -> str:
    if stream is None:
        return ""
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    parts: list[str] = []
    pending_line = ""
    while True:
        chunk = await stream.read(_CHUNK_BYTES)
        if not chunk:
            break
        text = decoder.decode(chunk)
        if not text:
            continue
        parts.append(text)
        if callback is None:
            continue
        pending_line += text
        lines = pending_line.splitlines(keepends=True)
        pending_line = ""
        if lines and not lines[-1].endswith(("\n", "\r")):
            pending_line = lines.pop()
        for line in lines:
            await _emit_line(line.rstrip("\r\n"), callback)
    tail = decoder.decode(b"", final=True)
    if tail:
        parts.append(tail)
        pending_line += tail
    if pending_line:
        await _emit_line(pending_line.rstrip("\r\n"), callback)
    return "".join(parts)


async def run_command(
    *,
    cmd: list[str],
    cwd: Path,
    timeout_seconds: int,
    on_stdout_line: Callable[[str], Awaitable[None] | None] | None = None,
) -> RunResult:
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_task = asyncio.create_task(_read_stream(process.stdout, callback=on_stdout_line))
    stderr_task = asyncio.create_task(_read_stream(process.stderr))
    timed_out = False
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        timed_out = True
        process.kill()
        await process.wait()
    stdout_text, stderr_text = await asyncio.gather(stdout_task, stderr_task)
    return {
        "timed_out": timed_out,
        "returncode": process.returncode,
        "stdout": stdout_text,
        "stderr": stderr_text,
    }
