from __future__ import annotations

import asyncio
import codecs
import os
import tempfile
from pathlib import Path
from typing import Any

from bao.agent.tool_result import (
    INLINE_TOOL_RESULT_CHARS,
    ToolTextResult,
    cleanup_result_file,
    make_file_preview,
)

CHUNK_BYTES = 65536


async def await_pending_tasks(*tasks: asyncio.Task[int] | None) -> None:
    pending_tasks = [task for task in tasks if task is not None]
    if pending_tasks:
        await asyncio.gather(*pending_tasks, return_exceptions=True)


def read_inline_result(result: ToolTextResult) -> str | None:
    if result.chars > INLINE_TOOL_RESULT_CHARS:
        return None
    text = result.path.read_text(encoding="utf-8", errors="replace")
    cleanup_result_file(result)
    return text or "(no output)"


async def drain_stream_to_file(
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
            chunk = await stream.read(CHUNK_BYTES)
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


def make_temp_path(prefix: str) -> Path:
    fd, raw_path = tempfile.mkstemp(prefix=prefix, suffix=".txt")
    os.close(fd)
    return Path(raw_path)


def cleanup_temp_path(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def compose_result_file(
    stdout_path: Path,
    stderr_path: Path,
    *,
    stdout_chars: int,
    stderr_chars: int,
    return_code: int,
) -> ToolTextResult:
    result_path = make_temp_path("bao_exec_result_")
    total_chars = 0
    with result_path.open("w", encoding="utf-8") as out_handle:
        total_chars += copy_text_file(stdout_path, out_handle)
        if stderr_chars > 0:
            prefix = "STDERR:\n"
            out_handle.write(prefix)
            total_chars += len(prefix)
            total_chars += copy_text_file(stderr_path, out_handle)
        if return_code != 0:
            exit_line = f"\nExit code: {return_code}"
            out_handle.write(exit_line)
            total_chars += len(exit_line)
    if total_chars == 0:
        result_path.write_text("(no output)", encoding="utf-8")
        total_chars = len("(no output)")
    excerpt = make_file_preview(result_path, min(2000, total_chars))
    return ToolTextResult(path=result_path, chars=total_chars, excerpt=excerpt, cleanup=True)


def copy_text_file(source_path: Path, out_handle: Any) -> int:
    chars = 0
    with source_path.open("r", encoding="utf-8", errors="replace") as in_handle:
        while True:
            chunk = in_handle.read(CHUNK_BYTES)
            if not chunk:
                break
            out_handle.write(chunk)
            chars += len(chunk)
    return chars
