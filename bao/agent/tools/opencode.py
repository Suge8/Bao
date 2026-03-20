"""OpenCode CLI coding agent tool — thin subclass of BaseCodingAgentTool."""

import json
import uuid
from pathlib import Path
from typing import Any

from bao.agent.tools._coding_agent_schema import build_coding_agent_parameters
from bao.agent.tools._opencode_agents import resolve_agent_alias
from bao.agent.tools.coding_agent_base import (
    BaseCodingAgentTool,
    BaseCodingDetailsTool,
    DetailCache,
)
from bao.agent.tools.coding_session_store import CodingSessionStore

_opencode_cache = DetailCache()


class OpenCodeTool(BaseCodingAgentTool):
    _SCHEMA_VERSION = 1

    def __init__(
        self,
        workspace: Path,
        allowed_dir: Path | None = None,
        default_timeout_seconds: int = 1800,
        session_store: CodingSessionStore | None = None,
    ):
        super().__init__(
            workspace=workspace,
            allowed_dir=allowed_dir,
            default_timeout_seconds=default_timeout_seconds,
            detail_cache=_opencode_cache,
            session_store=session_store,
        )
        self._agent_aliases_by_cwd: dict[str, dict[str, str]] = {}

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
        return build_coding_agent_parameters(
            prompt_description="Task prompt sent to OpenCode",
            session_description="Optional explicit OpenCode session ID to continue",
            model_description=(
                "Optional explicit model override in provider/model format. "
                "Omit it to use the backend or CLI default model."
            ),
            extra_properties={
                "fork": {
                    "type": "boolean",
                    "description": "Fork when continuing from a session",
                },
                "agent": {
                    "type": "string",
                    "description": "Optional OpenCode agent (for example: build, plan)",
                },
            },
        )

    # -- hook implementations --

    async def _prepare_extra_params(
        self, *, cwd: Path, timeout: int, extra_params: dict[str, Any]
    ) -> dict[str, Any]:
        agent = extra_params.get("agent")
        if not isinstance(agent, str) or not agent.strip():
            return extra_params

        prepared = dict(extra_params)
        prepared["agent"] = await resolve_agent_alias(
            cache=self._agent_aliases_by_cwd,
            cwd=cwd,
            agent_name=agent,
            timeout_seconds=min(timeout, 30),
            run_command=self._run_command,
        )
        return prepared

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
            title = f"Bao:{context_key}:{uuid.uuid4().hex[:8]}"
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
        for limit in (20, 100):
            cmd = ["opencode", "session", "list", "--format", "json", "-n", str(limit)]
            result = await self._run_command(
                cmd=cmd,
                cwd=cwd,
                timeout_seconds=min(timeout_seconds, 30),
            )
            if result["timed_out"] or result["returncode"] != 0:
                return None
            try:
                sessions = json.loads(result["stdout"])
            except (json.JSONDecodeError, ValueError):
                continue
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
                f"Use coding_agent_details with request_id '{request_id}', "
                f"or inspect session '{session_id}' via `opencode export`."
            )
        return (
            "Detailed output omitted to protect context budget. "
            f"Use coding_agent_details with request_id '{request_id}' to view full stdout/stderr."
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
