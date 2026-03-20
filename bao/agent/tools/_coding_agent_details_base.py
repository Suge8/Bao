from __future__ import annotations

import json
from abc import ABC
from contextvars import ContextVar
from typing import Any

from bao.agent.tool_result import ToolResultValue, maybe_temp_text_result
from bao.agent.tools._coding_agent_cache import DetailCache, DetailRecord
from bao.agent.tools.base import Tool


class BaseCodingDetailsTool(Tool, ABC):
    """Abstract base for the *_details companion tool."""

    def __init__(self, *, detail_cache: DetailCache, default_max_chars: int = 12000):
        self.detail_cache = detail_cache
        self.default_max_chars = max(200, int(default_max_chars))
        self._channel: ContextVar[str] = ContextVar("coding_details_channel", default="hub")
        self._chat_id: ContextVar[str] = ContextVar("coding_details_chat_id", default="direct")
        self._context_key: ContextVar[str] = ContextVar(
            "coding_details_context_key", default="hub:direct"
        )

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        self._channel.set(channel)
        self._chat_id.set(chat_id)
        self._context_key.set(session_key or f"{channel}:{chat_id}")

    @property
    def _tool_label(self) -> str:
        raise NotImplementedError

    @property
    def _meta_prefix(self) -> str:
        raise NotImplementedError

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "request_id": {
                    "type": "string",
                    "description": f"Preferred: request_id from {self._meta_prefix.replace('_DETAIL', '')}",
                },
                "session_id": {
                    "type": "string",
                    "description": f"Fallback: {self._tool_label} session id",
                },
                "max_chars": {
                    "type": "integer",
                    "minimum": 200,
                    "maximum": 50000,
                    "description": "Max chars for stdout/stderr in response",
                },
                "include_stderr": {
                    "type": "boolean",
                    "description": "Whether to include stderr content",
                },
                "response_format": {
                    "type": "string",
                    "enum": ["hybrid", "json", "text"],
                    "description": "Return format: hybrid (default), json, or text",
                },
            },
            "required": [],
        }

    @staticmethod
    def _clip_detail_text(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        omitted = len(text) - max_chars
        return text[:max_chars] + f"\n... (truncated {omitted} chars)"

    def _build_payload(
        self,
        *,
        record: DetailRecord,
        stdout: str,
        stderr: str,
    ) -> dict[str, Any]:
        return {
            "request_id": record["request_id"],
            "status": record["status"],
            "session_id": record["session_id"],
            "project_path": record["project_path"],
            "command_preview": record["command_preview"],
            "summary": record["summary"],
            "attempts": record["attempts"],
            "duration_ms": record["duration_ms"],
            "exit_code": record["exit_code"],
            "cache_truncated": record["cache_truncated"],
            "stdout": stdout,
            "stderr": stderr,
        }

    def _render_detail_response(
        self,
        *,
        payload: dict[str, Any],
        response_format: str,
        prefix: str = "bao_coding_details_",
    ) -> ToolResultValue:
        if response_format == "json":
            return maybe_temp_text_result(
                json.dumps(payload, ensure_ascii=False),
                prefix=prefix,
            )

        title = (
            f"{self._tool_label} details: request_id={payload['request_id']} "
            f"status={payload['status']}"
        )
        parts: list[str] = [title, "Summary:", str(payload["summary"])]
        if response_format == "hybrid":
            parts.insert(1, f"{self._meta_prefix}=" + json.dumps(payload, ensure_ascii=False))
        stdout = str(payload.get("stdout", ""))
        stderr = str(payload.get("stderr", ""))
        if stdout:
            parts.extend(["Output:", stdout])
        if stderr:
            parts.extend(["STDERR:", stderr])
        return maybe_temp_text_result("\n\n".join(str(part) for part in parts), prefix=prefix)

    async def execute(self, **kwargs: Any) -> ToolResultValue:
        request_id = kwargs.get("request_id")
        if request_id is not None and not isinstance(request_id, str):
            return "Error: request_id must be a string"

        session_id = kwargs.get("session_id")
        if session_id is not None and not isinstance(session_id, str):
            return "Error: session_id must be a string"

        max_chars = kwargs.get("max_chars", self.default_max_chars)
        if not isinstance(max_chars, int):
            return "Error: max_chars must be an integer"
        max_chars = max(200, min(max_chars, 50000))

        include_stderr = kwargs.get("include_stderr", True)
        if not isinstance(include_stderr, bool):
            return "Error: include_stderr must be a boolean"

        response_format = kwargs.get("response_format", "hybrid")
        if response_format not in ("hybrid", "json", "text"):
            return "Error: response_format must be one of: hybrid, json, text"

        context_key = self._context_key.get()
        record = self.detail_cache.lookup(
            request_id=request_id, session_id=session_id, context_key=context_key
        )
        if not record:
            return (
                f"No {self._tool_label} detail record found. Provide request_id/session_id, "
                f"or run {self.name.replace('_details', '')} first in this chat context."
            )

        stdout = self._clip_detail_text(record["stdout"], max_chars)
        stderr = record["stderr"] if include_stderr else ""
        if stderr:
            stderr = self._clip_detail_text(stderr, max_chars)
        payload = self._build_payload(record=record, stdout=stdout, stderr=stderr)
        return self._render_detail_response(
            payload=payload,
            response_format=response_format,
            prefix="bao_coding_details_",
        )
