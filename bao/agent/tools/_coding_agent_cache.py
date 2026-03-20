from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import TypedDict

DETAIL_CACHE_LIMIT = 128
DETAIL_CACHE_TEXT_MAX = 120_000
MIN_TOOL_TIMEOUT_SECONDS = 30
MAX_TOOL_TIMEOUT_SECONDS = 1800


class DetailRecord(TypedDict):
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


class RunResult(TypedDict):
    timed_out: bool
    returncode: int | None
    stdout: str
    stderr: str


@dataclass(frozen=True)
class DetailRecordInput:
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


class DetailCache:
    """LRU detail cache shared between a coding-agent tool and its details tool."""

    def __init__(self, limit: int = DETAIL_CACHE_LIMIT, text_max: int = DETAIL_CACHE_TEXT_MAX):
        self._limit = limit
        self._text_max = text_max
        self._cache: dict[str, DetailRecord] = {}
        self._order: deque[str] = deque()
        self._last_by_context: dict[str, str] = {}
        self._last_by_session: dict[str, str] = {}

    def _trim_text(self, text: str) -> tuple[str, bool]:
        if len(text) <= self._text_max:
            return text, False
        omitted = len(text) - self._text_max
        return text[: self._text_max] + f"\n... (detail cache truncated {omitted} chars)", True

    def store(self, record: DetailRecord) -> None:
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
    ) -> DetailRecord | None:
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

    def build_detail_record(self, record_input: DetailRecordInput) -> None:
        clipped_stdout, stdout_trunc = self._trim_text(record_input.stdout)
        clipped_stderr, stderr_trunc = self._trim_text(record_input.stderr)
        self.store(
            {
                "request_id": record_input.request_id,
                "context_key": record_input.context_key,
                "session_id": record_input.session_id,
                "project_path": record_input.project_path,
                "status": record_input.status,
                "command_preview": record_input.command_preview,
                "stdout": clipped_stdout,
                "stderr": clipped_stderr,
                "summary": record_input.summary,
                "attempts": record_input.attempts,
                "duration_ms": record_input.duration_ms,
                "exit_code": record_input.exit_code,
                "created_at": int(time.time()),
                "cache_truncated": stdout_trunc or stderr_trunc,
            }
        )
