"""Claude Code CLI coding agent tool — thin subclass of BaseCodingAgentTool."""

import json
import uuid
from pathlib import Path
from typing import Any

from bao.agent.tools.coding_agent_base import (
    BaseCodingAgentTool,
    BaseCodingDetailsTool,
    DetailCache,
)

_claudecode_cache = DetailCache()


class ClaudeCodeTool(BaseCodingAgentTool):
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
            detail_cache=_claudecode_cache,
        )

    @property
    def name(self) -> str:
        return "claudecode"

    @property
    def description(self) -> str:
        return (
            "Delegate coding tasks to Claude Code CLI (`claude -p`) with per-chat session tracking. "
            "Use for code writing, refactoring, debugging, and iterative follow-ups."
        )

    @property
    def cli_binary(self) -> str:
        return "claude"

    @property
    def _tool_label(self) -> str:
        return "Claude Code"

    @property
    def _meta_prefix(self) -> str:
        return "CLAUDECODE_META"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Task prompt sent to Claude Code",
                    "minLength": 1,
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional project directory (defaults to workspace)",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional explicit Claude Code session ID to continue",
                },
                "continue_session": {
                    "type": "boolean",
                    "description": "Continue previous chat-specific session when available",
                },
                "model": {
                    "type": "string",
                    "description": "Optional model name",
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

    def _build_command(
        self,
        *,
        prompt: str,
        resolved_session: str | None,
        model: str | None,
        context_key: str,
        extra_params: dict[str, Any],
    ) -> tuple[list[str], dict[str, Any]]:
        del context_key, extra_params

        cmd = ["claude", "-p", "--output-format", "json"]
        if model:
            cmd.extend(["--model", model])

        if resolved_session:
            cmd.extend(["--resume", resolved_session])
            cmd.append(prompt)
            return cmd, {"session_id": resolved_session}

        new_session = str(uuid.uuid4())
        cmd.extend(["--session-id", new_session, prompt])
        return cmd, {"session_id": new_session}

    async def _extract_output(self, *, stdout_text: str, exec_state: dict[str, Any]) -> str:
        raw_stdout = stdout_text.strip()
        if raw_stdout:
            exec_state["raw_stdout"] = raw_stdout
        parsed_text, parsed_session = self._extract_contract_fields(stdout_text)
        if parsed_session:
            exec_state["session_id_from_output"] = parsed_session
        return parsed_text or raw_stdout or "(no output)"

    async def _resolve_session_after_success(
        self,
        *,
        stdout_text: str,
        resolved_session: str | None,
        cwd: Path,
        exec_state: dict[str, Any],
        timeout: int,
    ) -> str | None:
        del stdout_text, cwd, timeout
        sid_from_output = exec_state.get("session_id_from_output")
        if isinstance(sid_from_output, str) and sid_from_output.strip():
            return sid_from_output.strip()
        if resolved_session:
            return resolved_session
        sid = exec_state.get("session_id")
        if isinstance(sid, str) and sid:
            return sid
        return None

    def _detail_stdout_for_cache(
        self,
        *,
        final_output: str,
        stdout_text: str,
        exec_state: dict[str, Any],
    ) -> str:
        raw_stdout = exec_state.get("raw_stdout")
        if isinstance(raw_stdout, str) and raw_stdout:
            return raw_stdout
        if stdout_text.strip():
            return stdout_text.strip()
        return final_output

    def _error_type_impl(self, stdout_text: str, stderr_text: str) -> str:
        lowered = f"{stdout_text}\n{stderr_text}".lower()
        if "auth" in lowered or "login" in lowered:
            return "auth_not_configured"
        if "permission" in lowered:
            return "permission_blocked"
        if "timed out" in lowered or "timeout" in lowered:
            return "timeout"
        return "execution_failed"

    def _build_failure_hints(self, stdout_text: str, stderr_text: str) -> list[str]:
        lowered = f"{stdout_text}\n{stderr_text}".lower()
        hints: list[str] = []
        if "auth" in lowered or "login" in lowered:
            hints.append("Run `claude auth login` to configure Claude Code authentication.")
        if "permission" in lowered:
            hints.append("Adjust Claude Code permission mode/settings for non-interactive runs.")
        return hints

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
                f"Use claudecode_details with request_id '{request_id}', "
                f"or resume session '{session_id}' via `claude --resume`."
            )
        return (
            "Detailed output omitted to protect context budget. "
            f"Use claudecode_details with request_id '{request_id}' to view full stdout/stderr."
        )

    @staticmethod
    def _extract_json_objects(text: str) -> list[dict[str, Any]]:
        s = text.strip()
        rows: list[dict[str, Any]] = []
        if not s:
            return rows

        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                return [obj]
            if isinstance(obj, list):
                return [x for x in obj if isinstance(x, dict)]
        except Exception:
            pass

        for line in text.splitlines():
            t = line.strip()
            if not t:
                continue
            try:
                obj = json.loads(t)
            except Exception:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
            elif isinstance(obj, list):
                rows.extend(x for x in obj if isinstance(x, dict))
        return rows

    @staticmethod
    def _find_first_string_by_keys(obj: Any, keys: tuple[str, ...]) -> str | None:
        if isinstance(obj, dict):
            for key in keys:
                val = obj.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            for val in obj.values():
                hit = ClaudeCodeTool._find_first_string_by_keys(val, keys)
                if hit:
                    return hit
        elif isinstance(obj, list):
            for item in obj:
                hit = ClaudeCodeTool._find_first_string_by_keys(item, keys)
                if hit:
                    return hit
        return None

    @staticmethod
    def _extract_contract_fields(text: str) -> tuple[str | None, str | None]:
        rows = ClaudeCodeTool._extract_json_objects(text)
        if not rows:
            return None, None

        primary = rows[-1]
        session_id = ClaudeCodeTool._extract_session_id(primary)
        if not session_id:
            for obj in reversed(rows[:-1]):
                session_id = ClaudeCodeTool._extract_session_id(obj)
                if session_id:
                    break

        result = primary.get("result") if isinstance(primary, dict) else None
        if isinstance(result, str) and result.strip():
            return result.strip(), session_id
        for obj in reversed(rows[:-1]):
            candidate = obj.get("result") if isinstance(obj, dict) else None
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip(), session_id

        return ClaudeCodeTool._extract_text_fallback(rows), session_id

    @staticmethod
    def _extract_session_id(obj: dict[str, Any]) -> str | None:
        direct = obj.get("session_id")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        camel = obj.get("sessionId")
        if isinstance(camel, str) and camel.strip():
            return camel.strip()
        return None

    @staticmethod
    def _extract_text_fallback(rows: list[dict[str, Any]]) -> str | None:
        candidates: list[str] = []
        for obj in rows:
            hit = ClaudeCodeTool._find_first_string_by_keys(
                obj,
                (
                    "message",
                    "content",
                    "text",
                    "output",
                    "response",
                    "final_message",
                    "finalMessage",
                ),
            )
            if hit:
                candidates.append(hit)
        return candidates[-1] if candidates else None


class ClaudeCodeDetailsTool(BaseCodingDetailsTool):
    def __init__(self, default_max_chars: int = 12000):
        super().__init__(detail_cache=_claudecode_cache, default_max_chars=default_max_chars)

    @property
    def name(self) -> str:
        return "claudecode_details"

    @property
    def description(self) -> str:
        return (
            "Fetch cached detailed Claude Code stdout/stderr by request_id, session_id, "
            "or current chat context latest run."
        )

    @property
    def _tool_label(self) -> str:
        return "Claude Code"

    @property
    def _meta_prefix(self) -> str:
        return "CLAUDECODE_DETAIL_META"
