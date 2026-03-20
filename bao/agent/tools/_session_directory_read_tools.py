from __future__ import annotations

from typing import Any

from bao.agent.tools._session_directory_tool_base import (
    SessionDirectoryToolBase,
    build_status_payload,
    build_transcript_payload,
)
from bao.hub import TranscriptReadRequest

__all__ = [
    "SessionDefaultTool",
    "SessionLookupTool",
    "SessionRecentTool",
    "SessionResolveTool",
    "SessionStatusTool",
    "SessionTranscriptTool",
]


def _normalize_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


class SessionRecentTool(SessionDirectoryToolBase):
    @property
    def name(self) -> str:
        return "session_recent"

    @property
    def description(self) -> str:
        return "List recent sessions from the HubDirectory read-plane."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "description": "Maximum results."}
            },
        }

    async def execute(self, **kwargs: Any) -> str:
        result = self._call_directory("list_recent_sessions", limit=kwargs.get("limit"))
        return result if isinstance(result, str) else self._json(result)


class SessionLookupTool(SessionDirectoryToolBase):
    @property
    def name(self) -> str:
        return "session_lookup"

    @property
    def description(self) -> str:
        return "Look up sessions from the HubDirectory read-plane."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Lookup query."},
                "limit": {"type": "integer", "minimum": 1, "description": "Maximum results."},
                "channel": {"type": "string", "description": "Optional channel filter."},
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query")
        if not isinstance(query, str) or not query.strip():
            return "Error: query is required."
        result = self._call_directory(
            "lookup_sessions",
            query=query,
            limit=kwargs.get("limit"),
            channel=kwargs.get("channel"),
        )
        return result if isinstance(result, str) else self._json(result)


class SessionDefaultTool(SessionDirectoryToolBase):
    @property
    def name(self) -> str:
        return "session_default"

    @property
    def description(self) -> str:
        return "Resolve the default session from the HubDirectory read-plane."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Optional channel filter."},
                "scope": {"type": "string", "description": "Optional preference scope."},
            },
        }

    async def execute(self, **kwargs: Any) -> str:
        route = self._route.get()
        result = self._call_directory(
            "get_default_session",
            channel=kwargs.get("channel"),
            scope=kwargs.get("scope"),
            session_key=route.session_key,
        )
        return result if isinstance(result, str) else self._json(result)


class SessionResolveTool(SessionDirectoryToolBase):
    @property
    def name(self) -> str:
        return "session_resolve"

    @property
    def description(self) -> str:
        return "Resolve a stable session_ref through the HubDirectory read-plane."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_ref": {"type": "string", "description": "Stable session reference."}
            },
            "required": ["session_ref"],
        }

    async def execute(self, **kwargs: Any) -> str:
        session_ref = kwargs.get("session_ref")
        if not isinstance(session_ref, str) or not session_ref.strip():
            return "Error: session_ref is required."
        result = self._call_directory("resolve_session_ref", session_ref=session_ref)
        return result if isinstance(result, str) else self._json(result)


class SessionStatusTool(SessionDirectoryToolBase):
    @property
    def name(self) -> str:
        return "session_status"

    @property
    def description(self) -> str:
        return "Read a concise status snapshot for another session."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_key": {"type": "string", "description": "Explicit target session key."},
                "session_ref": {"type": "string", "description": "Stable target session ref."},
            },
        }

    async def execute(self, **kwargs: Any) -> str:
        session_key, resolved = self._resolve_target(
            session_key=kwargs.get("session_key"),
            session_ref=kwargs.get("session_ref"),
        )
        if not session_key:
            return "Error: session_status requires session_key or a resolvable session_ref."
        entry = self._call_directory("get_session", key=session_key)
        if isinstance(entry, str):
            return entry
        if not isinstance(entry, dict) or not entry:
            return "Error: session not found."
        return self._json(
            build_status_payload(session_key=session_key, entry=entry, resolved=resolved)
        )


class SessionTranscriptTool(SessionDirectoryToolBase):
    @property
    def name(self) -> str:
        return "session_transcript"

    @property
    def description(self) -> str:
        return "Read another session transcript with cursor/transcript_ref support."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_key": {"type": "string", "description": "Explicit target session key."},
                "session_ref": {"type": "string", "description": "Stable target session ref."},
                "mode": {
                    "type": "string",
                    "enum": ["tail", "range", "full"],
                    "description": "Read mode.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Page size for tail/range.",
                },
                "cursor": {
                    "type": "string",
                    "description": "Cursor from a previous transcript page.",
                },
                "transcript_ref": {
                    "type": "string",
                    "description": "Consistency token from a previous transcript page.",
                },
                "raw": {
                    "type": "boolean",
                    "description": "Return raw message rows instead of compact items.",
                },
            },
        }

    async def execute(self, **kwargs: Any) -> str:
        session_key, resolved = self._resolve_target(
            session_key=kwargs.get("session_key"),
            session_ref=kwargs.get("session_ref"),
        )
        if not session_key:
            return "Error: session_transcript requires session_key or a resolvable session_ref."
        request = TranscriptReadRequest(
            mode=_normalize_text(kwargs.get("mode")) or "tail",
            limit=kwargs.get("limit") if isinstance(kwargs.get("limit"), int) else 0,
            cursor=_normalize_text(kwargs.get("cursor")),
            transcript_ref=_normalize_text(kwargs.get("transcript_ref")),
        )
        try:
            page = self._call_directory("read_transcript", key=session_key, request=request)
        except ValueError as exc:
            return f"Error: {exc}"
        if isinstance(page, str):
            return page
        payload = build_transcript_payload(
            page=page,
            session_ref=_normalize_text(resolved.get("session_ref")),
            raw=bool(kwargs.get("raw")),
        )
        return self._json(payload)
