"""Codex CLI coding agent tool — thin subclass of BaseCodingAgentTool."""

import tempfile
from pathlib import Path
from typing import Any

from bao.agent.tools._codex_jsonl import (
    extract_last_message_from_jsonl,
    extract_session_id_from_jsonl,
    read_last_output_file,
)
from bao.agent.tools._coding_agent_health import CodingBackendHealth
from bao.agent.tools._coding_agent_schema import build_coding_agent_parameters
from bao.agent.tools.coding_agent_base import (
    BaseCodingAgentTool,
    BaseCodingDetailsTool,
    DetailCache,
)
from bao.agent.tools.coding_session_store import CodingSessionStore

# Shared cache between CodexTool and CodexDetailsTool
_codex_cache = DetailCache()
_CODEX_MODE_OPTION_SUPPORT: dict[str, frozenset[str]] = {
    "start": frozenset({"model", "sandbox", "full_auto"}),
    "resume": frozenset({"model", "full_auto"}),
}
_CODEX_COMMON_FLAGS: tuple[str, ...] = ("--skip-git-repo-check",)


class CodexTool(BaseCodingAgentTool):
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
            detail_cache=_codex_cache,
            session_store=session_store,
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
        return build_coding_agent_parameters(
            prompt_description="Task prompt sent to Codex",
            session_description="Optional explicit Codex session id to continue",
            model_description="Optional explicit model override. Omit it to use the Codex CLI default model.",
            extra_properties={
                "sandbox": {
                    "type": "string",
                    "enum": ["read-only", "workspace-write", "danger-full-access"],
                    "description": "Codex sandbox mode",
                },
                "full_auto": {
                    "type": "boolean",
                    "description": "Enable Codex --full-auto for lower-friction automation",
                },
            },
        )

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
        mode = "resume" if resolved_session else "start"
        cmd = ["codex", "exec", *_CODEX_COMMON_FLAGS]
        if mode == "resume":
            cmd.append("resume")
        cmd.extend(["--json", "-o", output_file])
        supported = _CODEX_MODE_OPTION_SUPPORT[mode]
        if model and "model" in supported:
            cmd.extend(["-m", model])
        if sandbox and "sandbox" in supported:
            cmd.extend(["-s", sandbox])
        if full_auto and "full_auto" in supported:
            cmd.append("--full-auto")
        if resolved_session:
            cmd.extend([resolved_session, prompt])
        else:
            cmd.append(prompt)
        return cmd, {"output_file": output_file, "mode": mode}

    async def _extract_output(self, *, stdout_text: str, exec_state: dict[str, Any]) -> str:
        """On success: file > JSONL > raw. On failure: JSONL > raw > file."""
        output_file = exec_state.get("output_file", "")
        is_failure = exec_state.get("_returncode", 0) != 0
        file_content = read_last_output_file(output_file)
        jsonl_content = extract_last_message_from_jsonl(stdout_text)
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
        parsed = extract_session_id_from_jsonl(stdout_text)
        return parsed or resolved_session

    def _cleanup(self, exec_state: dict[str, Any]) -> None:
        output_file = exec_state.get("output_file", "")
        if output_file:
            Path(output_file).unlink(missing_ok=True)

    def _error_type_impl(self, stdout_text: str, stderr_text: str) -> str:
        lowered = f"{stdout_text}\n{stderr_text}".lower()
        if "未配置模型" in lowered or "model" in lowered and "not configured" in lowered:
            return "model_not_available"
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
        if "未配置模型" in lowered or "model" in lowered and "not configured" in lowered:
            hints.append(
                "Set a supported Codex model explicitly with the tool `model` parameter or fix ~/.codex/config.toml."
            )
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

    async def _probe_backend_health(self, timeout_seconds: int) -> CodingBackendHealth:
        tmp = tempfile.NamedTemporaryFile(prefix="bao_codex_probe_", suffix=".txt", delete=False)
        output_file = tmp.name
        tmp.close()
        cmd = [
            "codex",
            "exec",
            *_CODEX_COMMON_FLAGS,
            "--sandbox",
            "read-only",
            "--json",
            "-o",
            output_file,
            "Reply with OK.",
        ]
        try:
            result = await self._run_command(
                cmd=cmd,
                cwd=self.workspace,
                timeout_seconds=max(5, min(timeout_seconds, 30)),
            )
        finally:
            Path(output_file).unlink(missing_ok=True)
        stdout_text = result["stdout"]
        stderr_text = result["stderr"]
        if result["timed_out"]:
            return CodingBackendHealth(
                backend=self.name,
                ready=False,
                error_type="timeout",
                message="Codex backend preflight timed out.",
            )
        if result["returncode"] == 0:
            return CodingBackendHealth(backend=self.name, ready=True)
        error_type = self._classify_error_type(stdout_text, stderr_text)
        summary = self._summarize_output(stdout_text, stderr_text, max_chars=240)
        return CodingBackendHealth(
            backend=self.name,
            ready=False,
            error_type=error_type,
            message=summary,
            hints=tuple(self._build_failure_hints(stdout_text, stderr_text)),
        )

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
