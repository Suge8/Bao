"""OpenCode CLI coding agent tool — thin subclass of BaseCodingAgentTool."""

import json
import uuid
from pathlib import Path
from typing import Any

from bao.agent.tools.coding_agent_base import (
    BaseCodingAgentTool,
    BaseCodingDetailsTool,
    DetailCache,
)

# Shared cache between OpenCodeTool and OpenCodeDetailsTool
_opencode_cache = DetailCache()


class OpenCodeTool(BaseCodingAgentTool):
    _SCHEMA_VERSION = 1

    def __init__(
        self,
        workspace: Path,
        allowed_dir: Path | None = None,
        default_timeout_seconds: int = 600,
    ):
        super().__init__(
            workspace=workspace,
            allowed_dir=allowed_dir,
            default_timeout_seconds=default_timeout_seconds,
            detail_cache=_opencode_cache,
        )

    # -- identity --

    @property
    def name(self) -> str:
        return "opencode"

    @property
    def description(self) -> str:
        return (
            "Delegate coding tasks to OpenCode CLI (`opencode run`) with per-chat session tracking. "
            "Use for code writing, refactoring, debugging, and follow-up iterations."
        )

    @property
    def cli_binary(self) -> str:
        return "opencode"

    @property
    def _tool_label(self) -> str:
        return "OpenCode"

    @property
    def _meta_prefix(self) -> str:
        return "OPENCODE_META"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Task prompt sent to OpenCode",
                    "minLength": 1,
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional project directory (defaults to workspace)",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional explicit OpenCode session ID to continue",
                },
                "continue_session": {
                    "type": "boolean",
                    "description": "Continue previous chat-specific session when available",
                },
                "fork": {
                    "type": "boolean",
                    "description": "Fork when continuing from a session",
                },
                "model": {
                    "type": "string",
                    "description": "Optional model in provider/model format",
                },
                "agent": {
                    "type": "string",
                    "description": "Optional OpenCode agent (for example: build, plan)",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 30,
                    "maximum": 1800,
                    "description": "Execution timeout in seconds (default 600)",
                },
                "response_format": {
                    "type": "string",
                    "enum": ["hybrid", "json", "text"],
                    "description": "Return format: hybrid (default), json, or text",
                },
                "max_retries": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 2,
                    "description": "Retry attempts on transient failures",
                },
                "max_output_chars": {
                    "type": "integer",
                    "minimum": 200,
                    "maximum": 50000,
                    "description": "Max chars for stdout/stderr in tool output (default 4000)",
                },
                "include_details": {
                    "type": "boolean",
                    "description": "Include full tool stdout/stderr in output (default false)",
                },
            },
            "required": ["prompt"],
        }

    # -- hook implementations --

    def _validate_extra_params(self, kwargs: dict[str, Any]) -> str | None:
        fork = kwargs.get("fork", False)
        if not isinstance(fork, bool):
            return "Error: fork must be a boolean"
        agent = kwargs.get("agent")
        if agent is not None and not isinstance(agent, str):
            return "Error: agent must be a string"
        return None

    def _build_command(
        self,
        *,
        prompt: str,
        resolved_session: str | None,
        model: str | None,
        context_key: str,
        extra_params: dict[str, Any],
    ) -> tuple[list[str], dict[str, Any]]:
        fork = extra_params.get("fork", False)
        agent = extra_params.get("agent")

        cmd = ["opencode", "run", "--format", "default"]

        if resolved_session:
            cmd.extend(["--session", resolved_session])
            if fork:
                cmd.append("--fork")
            title = ""
        else:
            title = f"bao:{context_key}:{uuid.uuid4().hex[:8]}"
            cmd.extend(["--title", title])

        if model:
            cmd.extend(["--model", model])
        if agent:
            cmd.extend(["--agent", agent])

        cmd.append(prompt)
        return cmd, {"title": title}

    async def _resolve_session_after_success(
        self,
        *,
        stdout_text: str,
        resolved_session: str | None,
        cwd: Path,
        exec_state: dict[str, Any],
        timeout: int,
    ) -> str | None:
        if resolved_session:
            return resolved_session
        title = exec_state.get("title", "")
        if title:
            return await self._resolve_session_by_title(cwd, title, timeout)
        return None

    async def _resolve_session_by_title(
        self, cwd: Path, title: str, timeout_seconds: int
    ) -> str | None:
        """Look up session ID by title via `opencode session list`."""
        cmd = ["opencode", "session", "list", "--format", "json", "-n", "20"]
        result = await self._run_command(cmd=cmd, cwd=cwd, timeout_seconds=min(timeout_seconds, 30))
        if result["timed_out"] or result["returncode"] != 0:
            return None
        try:
            sessions = json.loads(result["stdout"])
        except (json.JSONDecodeError, ValueError):
            return None
        if isinstance(sessions, list):
            for s in sessions:
                if isinstance(s, dict) and s.get("title") == title:
                    sid = s.get("id") or s.get("session_id")
                    if isinstance(sid, str) and sid:
                        return sid
        return None

    def _error_type_impl(self, stdout_text: str, stderr_text: str) -> str:
        lowered = f"{stdout_text}\n{stderr_text}".lower()
        if "no providers" in lowered:
            return "provider_not_configured"
        if "permission" in lowered and "ask" in lowered:
            return "permission_prompt_blocked"
        if "timed out" in lowered or "timeout" in lowered:
            return "timeout"
        return "execution_failed"

    def _build_failure_hints(self, stdout_text: str, stderr_text: str) -> list[str]:
        lowered = f"{stdout_text}\n{stderr_text}".lower()
        hints: list[str] = []
        if "no providers" in lowered:
            hints.append("Run `opencode auth login` to configure a provider.")
        if "permission" in lowered and "ask" in lowered:
            hints.append(
                "Set project opencode.json permissions to allow file writes, "
                "or pass explicit confirmation flags."
            )
        return hints

    def _extra_payload_fields(self, extra_params: dict[str, Any]) -> dict[str, Any]:
        agent = extra_params.get("agent")
        return {"agent": agent} if agent else {}

    def _extra_meta_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent = payload.get("agent")
        return {"agent": agent} if agent else {}

    def _build_details_hint(
        self,
        request_id: str,
        session_id: str | None,
        include_details: bool,
        details_available: bool,
    ) -> str | None:
        if include_details or not details_available:
            return None
        if session_id:
            return (
                "Detailed output omitted to protect context budget. "
                f"Use opencode_details with request_id '{request_id}', "
                f"or inspect session '{session_id}' via `opencode export`."
            )
        return (
            "Detailed output omitted to protect context budget. "
            f"Use opencode_details with request_id '{request_id}' to view full stdout/stderr."
        )


class OpenCodeDetailsTool(BaseCodingDetailsTool):
    def __init__(self, default_max_chars: int = 12000):
        super().__init__(detail_cache=_opencode_cache, default_max_chars=default_max_chars)

    @property
    def name(self) -> str:
        return "opencode_details"

    @property
    def description(self) -> str:
        return (
            "Fetch cached detailed OpenCode stdout/stderr by request_id, session_id, "
            "or current chat context latest run."
        )

    @property
    def _tool_label(self) -> str:
        return "OpenCode"

    @property
    def _meta_prefix(self) -> str:
        return "OPENCODE_DETAIL_META"
