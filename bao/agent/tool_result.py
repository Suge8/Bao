from __future__ import annotations

import codecs
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

INLINE_TOOL_RESULT_CHARS = 8000
DEFAULT_RESULT_EXCERPT_CHARS = 2000


@dataclass(slots=True)
class ToolTextResult:
    path: Path
    chars: int
    excerpt: str = ""
    cleanup: bool = False


ToolResultValue = str | ToolTextResult


def tool_result_excerpt(result: ToolResultValue | object) -> str:
    if isinstance(result, ToolTextResult):
        return result.excerpt
    if isinstance(result, str):
        return result
    return str(result)


def read_head_chars(path: Path, max_chars: int) -> str:
    limit = max(0, int(max_chars))
    if limit == 0:
        return ""
    chunks: list[str] = []
    total = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        while total < limit:
            piece = handle.read(min(4096, limit - total))
            if not piece:
                break
            chunks.append(piece)
            total += len(piece)
    return "".join(chunks)


def read_tail_chars(path: Path, max_chars: int) -> str:
    limit = max(0, int(max_chars))
    if limit == 0:
        return ""
    approx_bytes = max(4096, limit * 4)
    with path.open("rb") as handle:
        handle.seek(0, 2)
        file_size = handle.tell()
        start = max(0, file_size - approx_bytes)
        handle.seek(start)
        data = handle.read()
    text = data.decode("utf-8", errors="replace")
    return text[-limit:]


def count_utf8_chars(path: Path) -> int:
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    chars = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            chars += len(decoder.decode(chunk))
        chars += len(decoder.decode(b"", final=True))
    return chars


def make_preview(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    error_lines = [
        line
        for line in text.splitlines()
        if any(
            kw in line.lower()
            for kw in ("error", "traceback", "exception", "failed", "permission denied")
        )
    ]

    head = text[:half].rsplit("\n", 1)[0] if "\n" in text[:half] else text[:half]
    tail = text[-half:].split("\n", 1)[-1] if "\n" in text[-half:] else text[-half:]
    parts = [head, "...", tail]
    if error_lines:
        parts.append(f"[Key errors:\n{chr(10).join(error_lines[:5])}]")
    return "\n".join(parts)


def make_file_preview(path: Path, max_chars: int) -> str:
    limit = max(0, int(max_chars))
    if limit == 0:
        return ""
    head = read_head_chars(path, limit)
    if len(head) < limit:
        return head
    tail = read_tail_chars(path, limit)
    if not tail or tail == head[-len(tail) :]:
        return head
    return make_preview(head + "\n...\n" + tail, limit)


def cleanup_result_file(result: ToolTextResult) -> None:
    if not result.cleanup:
        return
    try:
        result.path.unlink(missing_ok=True)
    except Exception:
        pass


def maybe_file_text_result(
    path: Path,
    *,
    inline_chars: int = INLINE_TOOL_RESULT_CHARS,
    excerpt_chars: int = DEFAULT_RESULT_EXCERPT_CHARS,
    cleanup: bool = False,
) -> ToolResultValue:
    inline_limit = max(1, int(inline_chars))
    if path.stat().st_size <= inline_limit:
        return path.read_text(encoding="utf-8")
    char_count = count_utf8_chars(path)
    if char_count <= inline_limit:
        return path.read_text(encoding="utf-8")
    excerpt_limit = min(char_count, max(1, int(excerpt_chars)))
    excerpt = make_file_preview(path, excerpt_limit)
    return ToolTextResult(path=path, chars=char_count, excerpt=excerpt, cleanup=cleanup)


def maybe_temp_text_result(
    text: str,
    *,
    prefix: str = "bao_tool_",
    inline_chars: int = INLINE_TOOL_RESULT_CHARS,
    excerpt_chars: int = DEFAULT_RESULT_EXCERPT_CHARS,
) -> ToolResultValue:
    if len(text) <= max(1, int(inline_chars)):
        return text
    fd, raw_path = tempfile.mkstemp(prefix=prefix, suffix=".txt")
    os.close(fd)
    path = Path(raw_path)
    path.write_text(text, encoding="utf-8")
    excerpt = make_preview(text, min(len(text), max(1, int(excerpt_chars))))
    return ToolTextResult(path=path, chars=len(text), excerpt=excerpt, cleanup=True)
