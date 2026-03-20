from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bao.agent.tool_result import ToolResultValue, maybe_temp_text_result
from bao.agent.tools.base import Tool

if TYPE_CHECKING:
    from bao.agent.tools.coding_agent import CodingAgentTool


class CodingAgentDetailsTool(Tool):
    def __init__(self, parent: "CodingAgentTool"):
        self._parent = parent

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        self._parent.set_context(channel, chat_id, session_key=session_key)

    @property
    def name(self) -> str:
        return "coding_agent_details"

    @property
    def description(self) -> str:
        return (
            "Fetch cached stdout/stderr from a previous coding_agent run by "
            "request_id or session_id."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "request_id": {
                    "type": "string",
                    "description": "Request ID from coding_agent output",
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID fallback",
                },
                "agent": {
                    "type": "string",
                    "enum": self._parent.available_backends,
                    "description": "Optional backend filter to disambiguate session_id lookups",
                },
                "max_chars": {
                    "type": "integer",
                    "minimum": 200,
                    "maximum": 50000,
                    "description": "Max output chars",
                },
                "include_stderr": {
                    "type": "boolean",
                    "description": "Include stderr content",
                },
                "response_format": {
                    "type": "string",
                    "enum": ["hybrid", "json", "text"],
                    "description": "Output format",
                },
            },
            "required": [],
        }

    @staticmethod
    def _clip_text(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars]

    @classmethod
    def _render_fallback_record(
        cls,
        *,
        agent_name: str,
        record: dict[str, Any],
        max_chars: int,
        include_stderr: bool,
    ) -> ToolResultValue:
        stdout = cls._clip_text(str(record.get("stdout", "")), max_chars)
        stderr = str(record.get("stderr", ""))
        parts = [f"[{agent_name}] request_id={record.get('request_id', '?')}"]
        parts.append(f"Status: {record.get('status', '?')}")
        if stdout:
            parts.append(f"Output:\n{stdout}")
        if include_stderr and stderr:
            parts.append(f"Stderr:\n{cls._clip_text(stderr, max_chars)}")
        return maybe_temp_text_result("\n".join(parts), prefix="bao_coding_details_")

    async def execute(self, **kwargs: Any) -> ToolResultValue:
        request_id = kwargs.get("request_id")
        session_id = kwargs.get("session_id")
        agent_filter = kwargs.get("agent")

        if agent_filter is not None and not isinstance(agent_filter, str):
            return "Error: agent must be a string"
        if isinstance(agent_filter, str) and agent_filter not in self._parent._backends:
            available = ", ".join(self._parent._backends.keys()) or "none"
            return f"Error: agent must be one of: {available}"

        target_agents = (
            [agent_filter]
            if isinstance(agent_filter, str)
            else list(self._parent._detail_caches.keys())
        )
        matches: list[tuple[str, Any, Any]] = []

        for agent_name in target_agents:
            cache = self._parent._detail_caches.get(agent_name)
            if cache is None:
                continue
            backend = self._parent._backends.get(agent_name)
            if backend is None:
                continue
            context_key = backend._context_key.get()
            record = cache.lookup(
                context_key=context_key,
                request_id=request_id,
                session_id=session_id,
            )
            if not record:
                continue
            details_tool = self._parent._details_tools.get(agent_name)
            matches.append((agent_name, record, details_tool))

        if not request_id and session_id and not isinstance(agent_filter, str) and len(matches) > 1:
            backends = ", ".join(name for name, _, _ in matches)
            return (
                "Ambiguous session_id across backends. "
                f"Matched backends: {backends}. "
                "Please provide agent to disambiguate."
            )

        if matches:
            agent_name, record, details_tool = matches[0]
            if details_tool is not None:
                return await details_tool.execute(**kwargs)

            max_chars = kwargs.get("max_chars", 4000)
            if not isinstance(max_chars, int):
                max_chars = 4000
            max_chars = max(200, min(max_chars, 50000))
            return self._render_fallback_record(
                agent_name=agent_name,
                record=record,
                max_chars=max_chars,
                include_stderr=bool(kwargs.get("include_stderr")),
            )

        return "No cached details found for the given request_id/session_id."
