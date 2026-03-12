import importlib
import shutil
from pathlib import Path
from typing import Any

from loguru import logger

from bao.agent.tool_result import ToolResultValue, maybe_temp_text_result
from bao.agent.tools.base import Tool


class CodingAgentTool(Tool):
    def __init__(self, workspace: Path, allowed_dir: Path | None = None, **kwargs: Any):
        self._workspace = workspace
        self._allowed_dir = allowed_dir
        self._kwargs = kwargs
        self._backends: dict[str, Any] = {}
        self._detail_caches: dict[str, Any] = {}
        self._details_tools: dict[str, Any] = {}
        self._init_backends()

    def _init_backends(self) -> None:
        backend_specs = [
            (
                "opencode",
                "opencode",
                "bao.agent.tools.opencode",
                "OpenCodeTool",
                "OpenCodeDetailsTool",
            ),
            ("codex", "codex", "bao.agent.tools.codex", "CodexTool", "CodexDetailsTool"),
            (
                "claudecode",
                "claude",
                "bao.agent.tools.claudecode",
                "ClaudeCodeTool",
                "ClaudeCodeDetailsTool",
            ),
        ]

        for name, binary, module_path, tool_cls_name, details_cls_name in backend_specs:
            if not shutil.which(binary):
                continue

            try:
                module = importlib.import_module(module_path)
                backend_cls = getattr(module, tool_cls_name)
                backend = backend_cls(
                    workspace=self._workspace,
                    allowed_dir=self._allowed_dir,
                    **self._kwargs,
                )
                self._backends[name] = backend
                self._detail_caches[name] = backend.detail_cache

                details_cls = getattr(module, details_cls_name)
                self._details_tools[name] = details_cls()
            except Exception as e:
                logger.warning("⚠️ 编程代理初始化失败 / init failed: {} — {}", name, e)
                continue

    @property
    def available_backends(self) -> list[str]:
        return list(self._backends.keys())

    @property
    def name(self) -> str:
        return "coding_agent"

    @property
    def description(self) -> str:
        available = ", ".join(self._backends.keys()) or "none"
        return (
            f"Delegate coding tasks to a CLI coding agent backend. Available backends: {available}."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        agents = list(self._backends.keys())
        props: dict[str, Any] = {
            "agent": {
                "type": "string",
                "enum": agents,
                "description": (
                    "Backend to use. "
                    "opencode: fast iterative coding with broad tool support. "
                    "codex: balanced quality with sandbox/full_auto controls. "
                    "claudecode: stronger reasoning for architecture and reviews."
                ),
            },
            "prompt": {
                "type": "string",
                "description": "Task prompt for the coding agent",
                "minLength": 1,
            },
            "project_path": {
                "type": "string",
                "description": "Project directory (defaults to workspace)",
            },
            "session_id": {
                "type": "string",
                "description": "Session ID to continue a previous conversation",
            },
            "continue_session": {
                "type": "boolean",
                "description": "Continue previous chat-specific session",
            },
            "model": {
                "type": "string",
                "description": "Model name override",
            },
            "timeout_seconds": {
                "type": "integer",
                "minimum": 30,
                "maximum": 1800,
                "description": "Timeout in seconds (optional, default 1800)",
            },
            "response_format": {
                "type": "string",
                "enum": ["hybrid", "json", "text"],
                "description": "Output format (default: hybrid)",
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
                "description": "Max output chars (default 4000)",
            },
            "include_details": {
                "type": "boolean",
                "description": "Include full stdout/stderr (default false)",
            },
        }

        if "codex" in self._backends:
            props["sandbox"] = {
                "type": "string",
                "enum": ["read-only", "workspace-write", "danger-full-access"],
                "description": "Codex sandbox mode. Ignored unless agent='codex'.",
            }
            props["full_auto"] = {
                "type": "boolean",
                "description": "Codex full-auto mode. Ignored unless agent='codex'.",
            }

        if "opencode" in self._backends:
            props["opencode_agent"] = {
                "type": "string",
                "description": "OpenCode agent type (e.g. build, plan). Ignored unless agent='opencode'.",
            }
            props["fork"] = {
                "type": "boolean",
                "description": "Fork session when continuing. Ignored unless agent='opencode'.",
            }

        return {
            "type": "object",
            "properties": props,
            "required": ["agent", "prompt"],
        }

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        for backend in self._backends.values():
            backend.set_context(channel, chat_id, session_key)
        for details_tool in self._details_tools.values():
            details_tool.set_context(channel, chat_id, session_key)

    async def execute(self, **kwargs: Any) -> ToolResultValue:
        agent_name = kwargs.pop("agent", None)
        if not isinstance(agent_name, str) or agent_name not in self._backends:
            available = ", ".join(self._backends.keys()) or "none"
            return f"Error: agent must be one of: {available}"

        backend = self._backends[agent_name]

        if agent_name == "opencode":
            oc_agent = kwargs.pop("opencode_agent", None)
            if oc_agent is not None:
                kwargs["agent"] = oc_agent

        _param_backend = {
            "sandbox": "codex",
            "full_auto": "codex",
            "opencode_agent": "opencode",
            "fork": "opencode",
        }
        for key in _param_backend:
            if key in kwargs and agent_name != _param_backend[key]:
                kwargs.pop(key, None)

        return await backend.execute(**kwargs)


class CodingAgentDetailsTool(Tool):
    def __init__(self, parent: CodingAgentTool):
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
