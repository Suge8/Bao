"""Codex CLI coding agent tool — thin subclass of BaseCodingAgentTool."""

import json
import tempfile
from pathlib import Path
from typing import Any

from bao.agent.tools.coding_agent_base import (
    BaseCodingAgentTool,
    BaseCodingDetailsTool,
    DetailCache,
)

# Shared cache between CodexTool and CodexDetailsTool
_codex_cache = DetailCache()


class CodexTool(BaseCodingAgentTool):
    _SCHEMA_VERSION = 1

    def __init__(
        self,
        workspace: Path,
        allowed_dir: Path | None = None,
        default_timeout_seconds: int = 1800,
    ):
        super().__init__(
            workspace=workspace,
            allowed_dir=allowed_dir,
            default_timeout_seconds=default_timeout_seconds,
            detail_cache=_codex_cache,
        )

    # -- identity --

    @property
    def name(self) -> str:
        return "codex"

    @property
    def description(self) -> str:
        return (
            "Delegate coding tasks to Codex CLI (`codex exec`) with per-chat session tracking. "
            "Use for code writing, refactoring, debugging, and iterative follow-ups."
        )

    @property
    def cli_binary(self) -> str:
        return "codex"

    @property
    def _tool_label(self) -> str:
        return "Codex"

    @property
    def _meta_prefix(self) -> str:
        return "CODEX_META"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Task prompt sent to Codex",
                    "minLength": 1,
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional project directory (defaults to workspace)",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional explicit Codex session id to continue",
                },
                "continue_session": {
                    "type": "boolean",
                    "description": "Continue previous chat-specific session when available",
                },
                "model": {
                    "type": "string",
                    "description": "Optional model name",
                },
                "sandbox": {
                    "type": "string",
                    "enum": ["read-only", "workspace-write", "danger-full-access"],
                    "description": "Codex sandbox mode",
                },
                "full_auto": {
                    "type": "boolean",
                    "description": "Enable Codex --full-auto for lower-friction automation",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 30,
                    "maximum": 1800,
                    "description": "Execution timeout in seconds (default 1800)",
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

    # -- transient markers override (adds "overloaded") --

    _TRANSIENT_MARKERS: tuple[str, ...] = (
        "timeout",
        "timed out",
        "temporar",
        "rate limit",
        "429",
        "econnreset",
        "eai_again",
        "overloaded",
    )

    # -- hook implementations --

    def _validate_extra_params(self, kwargs: dict[str, Any]) -> str | None:
        sandbox = kwargs.get("sandbox")
        if sandbox is not None and sandbox not in (
            "read-only",
            "workspace-write",
            "danger-full-access",
        ):
            return "Error: sandbox must be one of: read-only, workspace-write, danger-full-access"
        full_auto = kwargs.get("full_auto", False)
        if not isinstance(full_auto, bool):
            return "Error: full_auto must be a boolean"
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
        sandbox = extra_params.get("sandbox")
        full_auto = extra_params.get("full_auto", False)

        tmp = tempfile.NamedTemporaryFile(prefix="bao_codex_last_", suffix=".txt", delete=False)
        output_file = tmp.name
        tmp.close()

        if resolved_session:
            cmd = ["codex", "exec", "resume", "--json", "-o", output_file]
            if model:
                cmd.extend(["-m", model])
            if sandbox:
                cmd.extend(["-s", sandbox])
            if full_auto:
                cmd.append("--full-auto")
            cmd.extend([resolved_session, prompt])
            return cmd, {"output_file": output_file}

        cmd = ["codex", "exec", "--json", "-o", output_file]
        if model:
            cmd.extend(["-m", model])
        if sandbox:
            cmd.extend(["-s", sandbox])
        if full_auto:
            cmd.append("--full-auto")
        cmd.append(prompt)
        return cmd, {"output_file": output_file}

    async def _extract_output(self, *, stdout_text: str, exec_state: dict[str, Any]) -> str:
        """On success: file > JSONL > raw. On failure: JSONL > raw > file."""
        output_file = exec_state.get("output_file", "")
        is_failure = exec_state.get("_returncode", 0) != 0
        file_content = self._read_last_output_file(output_file)
        jsonl_content = self._extract_last_message_from_jsonl(stdout_text)
        raw = stdout_text.strip()
        if is_failure:
            return jsonl_content or raw or file_content or "(no output)"
        return file_content or jsonl_content or raw or "(no output)"

    async def _resolve_session_after_success(
        self,
        *,
        stdout_text: str,
        resolved_session: str | None,
        cwd: Path,
        exec_state: dict[str, Any],
        timeout: int,
    ) -> str | None:
        parsed = self._extract_session_id_from_jsonl(stdout_text)
        return parsed or resolved_session

    def _cleanup(self, exec_state: dict[str, Any]) -> None:
        output_file = exec_state.get("output_file", "")
        if output_file:
            Path(output_file).unlink(missing_ok=True)

    def _error_type_impl(self, stdout_text: str, stderr_text: str) -> str:
        lowered = f"{stdout_text}\n{stderr_text}".lower()
        if "login" in lowered or "auth" in lowered or "api key" in lowered:
            return "auth_not_configured"
        if "permission" in lowered or "approval" in lowered:
            return "permission_blocked"
        if "timed out" in lowered or "timeout" in lowered:
            return "timeout"
        return "execution_failed"

    def _build_failure_hints(self, stdout_text: str, stderr_text: str) -> list[str]:
        lowered = f"{stdout_text}\n{stderr_text}".lower()
        hints: list[str] = []
        if "login" in lowered or "auth" in lowered or "api key" in lowered:
            hints.append(
                "Run `codex login` (or `codex login --with-api-key`) to configure authentication."
            )
        if "permission" in lowered or "approval" in lowered:
            hints.append(
                "Permission prompt blocked non-interactive run; "
                "enable full_auto explicitly or adjust Codex config profile."
            )
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
                f"Use coding_agent_details with request_id '{request_id}', "
                f"or resume session '{session_id}' via `codex exec resume`."
            )
        return (
            "Detailed output omitted to protect context budget. "
            f"Use coding_agent_details with request_id '{request_id}' to view full stdout/stderr."
        )

    # -- JSONL / output helpers --

    @staticmethod
    def _read_last_output_file(path: str) -> str:
        file_path = Path(path)
        if not file_path.exists():
            return ""
        try:
            return file_path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            return ""

    @staticmethod
    def _extract_json_objects(text: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except Exception:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
            elif isinstance(obj, list):
                rows.extend(x for x in obj if isinstance(x, dict))
        return rows

    @staticmethod
    def _extract_session_id_from_jsonl(text: str) -> str | None:
        rows = CodexTool._extract_json_objects(text)
        # Prefer thread_id from thread.started event (official Codex schema)
        for obj in rows:
            if obj.get("type") == "thread.started":
                tid = obj.get("thread_id") or obj.get("threadId")
                if isinstance(tid, str) and tid.strip():
                    return tid.strip()
        # Fallback: search all rows for any session/thread id key
        for obj in rows:
            sid = CodexTool._find_first_string_by_keys(
                obj,
                (
                    "thread_id",
                    "threadId",
                    "session_id",
                    "sessionId",
                    "conversation_id",
                    "conversationId",
                ),
            )
            if sid:
                return sid
        return None

    @staticmethod
    def _extract_last_message_from_jsonl(text: str) -> str | None:
        rows = CodexTool._extract_json_objects(text)
        candidates: list[str] = []
        for obj in rows:
            msg = CodexTool._find_first_string_by_keys(
                obj,
                (
                    "final_message",
                    "finalMessage",
                    "last_message",
                    "lastMessage",
                    "message",
                    "content",
                    "text",
                ),
            )
            if msg:
                candidates.append(msg)
        return candidates[-1] if candidates else None

    @staticmethod
    def _find_first_string_by_keys(obj: Any, keys: tuple[str, ...]) -> str | None:
        if isinstance(obj, dict):
            for key in keys:
                val = obj.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            for val in obj.values():
                hit = CodexTool._find_first_string_by_keys(val, keys)
                if hit:
                    return hit
        elif isinstance(obj, list):
            for item in obj:
                hit = CodexTool._find_first_string_by_keys(item, keys)
                if hit:
                    return hit
        return None


class CodexDetailsTool(BaseCodingDetailsTool):
    def __init__(self, default_max_chars: int = 12000):
        super().__init__(detail_cache=_codex_cache, default_max_chars=default_max_chars)

    @property
    def name(self) -> str:
        return "codex_details"

    @property
    def description(self) -> str:
        return (
            "Fetch cached detailed Codex stdout/stderr by request_id, session_id, "
            "or current chat context latest run."
        )

    @property
    def _tool_label(self) -> str:
        return "Codex"

    @property
    def _meta_prefix(self) -> str:
        return "CODEX_DETAIL_META"
