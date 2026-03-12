from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from time import time
from uuid import uuid4

from loguru import logger

from bao.agent.tool_result import (
    ToolResultValue,
    ToolTextResult,
    cleanup_result_file,
    make_file_preview,
    make_preview,
    read_head_chars,
)
from bao.utils.helpers import safe_filename


@dataclass
class ArtifactRef:
    path: Path
    kind: str
    size: int
    redacted: bool


@dataclass
class ToolOutputBudgetEvent:
    offloaded: bool = False
    offloaded_chars: int = 0
    hard_clipped: bool = False
    hard_clipped_chars: int = 0


class ArtifactStore:
    _KIND_DIRS: dict[str, str] = {
        "tool_output": "outputs",
        "evicted_messages": "evicted",
        "trajectory": "trajectory",
    }
    _SENSITIVE_PATTERNS: tuple[str, ...] = (
        r"-----BEGIN",
        r"PRIVATE KEY",
        r"xoxb-",
        r"ghp_",
        r"AKIA[0-9A-Z]{16}",
        r"AIza[0-9A-zA-Z\-_]{35}",
        r"(?im)^[\w\-]*(api[_-]?key|token|secret|password)[\w\-]*\s*=\s*\S",
    )

    def __init__(self, workspace: Path, session_key: str, retention_days: int = 7):
        self.workspace = workspace
        self.session_key = session_key
        self.retention_days = retention_days
        self.safe_session_key = safe_filename(session_key) or "session"
        self.context_root = self.workspace / ".bao" / "context"
        self.session_dir = self.context_root / self.safe_session_key

    def _write_file(self, kind: str, filename: str, content: str) -> Path:
        target_dir = self._kind_dir(kind)
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / filename
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def write_text(
        self, kind: str, name_hint: str, content: str, *, redacted: bool = False
    ) -> ArtifactRef:
        size = len(content)
        safe_hint = safe_filename(name_hint) or "artifact"

        if not redacted:
            redacted = self._is_sensitive(content) or any(
                tag in name_hint for tag in ("write_file", "edit_file")
            )
        if redacted:
            return ArtifactRef(path=Path(safe_hint), kind=kind, size=size, redacted=True)
        file_path = self._write_file(kind, f"{safe_hint}_{self._short_uuid()}.txt", content)
        return ArtifactRef(path=file_path, kind=kind, size=size, redacted=False)

    def write_text_file(
        self,
        kind: str,
        name_hint: str,
        source_path: Path,
        *,
        size: int,
        move_source: bool = True,
        redacted: bool | None = None,
    ) -> ArtifactRef:
        safe_hint = safe_filename(name_hint) or "artifact"
        if redacted is None:
            redacted = self._is_sensitive_file(source_path) or any(
                tag in name_hint for tag in ("write_file", "edit_file")
            )
        if redacted:
            return ArtifactRef(path=Path(safe_hint), kind=kind, size=size, redacted=True)
        target_dir = self._kind_dir(kind)
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{safe_hint}_{self._short_uuid()}.txt"
        if move_source:
            shutil.move(str(source_path), file_path)
        else:
            shutil.copyfile(source_path, file_path)
        return ArtifactRef(path=file_path, kind=kind, size=size, redacted=False)

    @staticmethod
    def _is_sensitive(content: str) -> bool:
        return any(re.search(pattern, content) for pattern in ArtifactStore._SENSITIVE_PATTERNS)

    @classmethod
    def _is_sensitive_file(cls, path: Path) -> bool:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if any(re.search(pattern, line) for pattern in cls._SENSITIVE_PATTERNS):
                        return True
        except Exception:
            return False
        return False

    def archive_json(self, kind: str, name_hint: str, obj: object) -> ArtifactRef:
        serialized = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
        safe_hint = safe_filename(name_hint) or "artifact"
        file_path = self._write_file(kind, f"{safe_hint}_{self._short_uuid()}.json", serialized)
        return ArtifactRef(path=file_path, kind=kind, size=len(serialized), redacted=False)

    def format_pointer(self, ref: ArtifactRef, preview_text: str = "", note: str = "") -> str:
        if ref.redacted:
            body = f"[{ref.kind} redacted: content not stored | ref: {ref.path.as_posix()}]"
            return f"{body}\n{preview_text}".rstrip()

        rel_path = self._workspace_relative(ref.path)
        header = f"[{ref.kind} offloaded: {ref.size} chars | ref: {rel_path}]"
        full_output = f"[Full output: {ref.path.resolve()}]"
        return f"{header}\n{preview_text}\n{full_output}".rstrip()

    def cleanup_session(self) -> None:
        try:
            shutil.rmtree(self.session_dir)
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.debug(
                "Failed to cleanup artifact session directory {}: {}", self.session_dir, exc
            )

    def cleanup_stale(self) -> None:
        if not self.context_root.exists():
            return

        ttl_seconds = self.retention_days * 24 * 60 * 60
        now = time()

        for child in self.context_root.iterdir():
            if not child.is_dir():
                continue
            try:
                if now - child.stat().st_mtime > ttl_seconds:
                    shutil.rmtree(child)
            except Exception as exc:
                logger.debug("Failed to cleanup stale artifact directory {}: {}", child, exc)

    def _kind_dir(self, kind: str) -> Path:
        return self.session_dir / self._KIND_DIRS.get(kind, "misc")

    @staticmethod
    def _short_uuid() -> str:
        return uuid4().hex[:8]

    def _workspace_relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.workspace))
        except ValueError:
            return str(path)


def hard_clip_tool_result(result: str, tool_name: str, hard_chars: int = 6000) -> tuple[str, int]:
    limit = max(500, int(hard_chars))
    if len(result) <= limit:
        return result, 0
    omitted = len(result) - limit
    clipped = result[:limit]
    suffix = (
        "\n... "
        f"(hard-truncated {omitted} chars for context safety from tool '{tool_name}'; "
        "request details explicitly if needed)"
    )
    return clipped + suffix, omitted


def apply_tool_output_budget(
    *,
    store: "ArtifactStore | None",
    tool_name: str,
    tool_call_id: str,
    result: ToolResultValue,
    offload_chars: int = 8000,
    preview_chars: int = 3000,
    hard_chars: int = 6000,
    ctx_mgmt: str = "auto",
) -> tuple[str, ToolOutputBudgetEvent]:
    event = ToolOutputBudgetEvent()
    if isinstance(result, ToolTextResult):
        try:
            if store is not None and ctx_mgmt in ("auto", "aggressive") and result.chars >= offload_chars:
                try:
                    preview = make_file_preview(result.path, preview_chars)
                    ref = store.write_text_file(
                        "tool_output",
                        f"{tool_name}_{tool_call_id}",
                        result.path,
                        size=result.chars,
                        move_source=result.cleanup,
                    )
                    event.offloaded = True
                    event.offloaded_chars = result.chars
                    return store.format_pointer(ref, preview), event
                except Exception as exc:
                    logger.debug("ctx[L1] offload failed for {}: {}", tool_name, exc)
            if result.chars <= hard_chars:
                return result.path.read_text(encoding="utf-8", errors="replace"), event
            preview = read_head_chars(result.path, hard_chars)
            omitted = max(0, result.chars - len(preview))
            clipped = preview + (
                "\n... "
                f"(hard-truncated {omitted} chars for context safety from tool '{tool_name}'; "
                "request details explicitly if needed)"
            )
            event.hard_clipped = True
            event.hard_clipped_chars = omitted
            return clipped, event
        finally:
            cleanup_result_file(result)

    processed = result
    if store is not None and ctx_mgmt in ("auto", "aggressive") and len(processed) >= offload_chars:
        try:
            preview = make_preview(processed, preview_chars)
            ref = store.write_text("tool_output", f"{tool_name}_{tool_call_id}", processed)
            processed = store.format_pointer(ref, preview)
            event.offloaded = True
            event.offloaded_chars = len(result)
        except Exception as exc:
            logger.debug("ctx[L1] offload failed for {}: {}", tool_name, exc)

    processed, omitted = hard_clip_tool_result(processed, tool_name=tool_name, hard_chars=hard_chars)
    if omitted > 0:
        event.hard_clipped = True
        event.hard_clipped_chars = omitted

    return processed, event
