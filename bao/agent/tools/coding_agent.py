import importlib
import json
import shutil
from pathlib import Path
from typing import Any

from loguru import logger

from bao.agent.tool_result import ToolResultValue
from bao.agent.tools._coding_agent_details import CodingAgentDetailsTool as _CodingAgentDetailsTool
from bao.agent.tools._coding_agent_health import CodingBackendHealth, format_backend_issue
from bao.agent.tools._coding_agent_schema import DEFAULT_MODEL_OVERRIDE_DESCRIPTION
from bao.agent.tools.base import Tool


class CodingAgentTool(Tool):
    _BACKEND_SPECS = (
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
    )

    def __init__(self, workspace: Path, allowed_dir: Path | None = None, **kwargs: Any):
        self._workspace = workspace
        self._allowed_dir = allowed_dir
        self._kwargs = kwargs
        self._backends: dict[str, Any] = {}
        self._detail_caches: dict[str, Any] = {}
        self._details_tools: dict[str, Any] = {}
        self._init_backends()

    def _init_backends(self) -> None:
        for name, binary, module_path, tool_cls_name, details_cls_name in self._BACKEND_SPECS:
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
        props = self._base_parameter_properties(agents)
        props.update(self._codex_parameter_properties())
        props.update(self._opencode_parameter_properties())
        return {
            "type": "object",
            "properties": props,
            "required": ["agent", "prompt"],
        }

    def _base_parameter_properties(self, agents: list[str]) -> dict[str, Any]:
        props = {
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
        }
        props.update(self._common_parameter_properties())
        return props

    @staticmethod
    def _common_parameter_properties() -> dict[str, Any]:
        return {
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
                "description": DEFAULT_MODEL_OVERRIDE_DESCRIPTION,
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
                "description": "Reserved compatibility field; hidden automatic retries are disabled",
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

    def _codex_parameter_properties(self) -> dict[str, Any]:
        if "codex" in self._backends:
            return {
                "sandbox": {
                    "type": "string",
                    "enum": ["read-only", "workspace-write", "danger-full-access"],
                    "description": "Codex sandbox mode. Ignored unless agent='codex'.",
                },
                "full_auto": {
                    "type": "boolean",
                    "description": "Codex full-auto mode. Ignored unless agent='codex'.",
                },
            }
        return {}

    def _opencode_parameter_properties(self) -> dict[str, Any]:
        if "opencode" in self._backends:
            return {
                "opencode_agent": {
                    "type": "string",
                    "description": (
                        "OpenCode agent type (e.g. build, plan). "
                        "Ignored unless agent='opencode'."
                    ),
                },
                "fork": {
                    "type": "boolean",
                    "description": "Fork session when continuing. Ignored unless agent='opencode'.",
                },
            }
        return {}

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        for backend in self._backends.values():
            backend.set_context(channel, chat_id, session_key)
        for details_tool in self._details_tools.values():
            details_tool.set_context(channel, chat_id, session_key)

    async def collect_backend_health(self, timeout_seconds: int = 20) -> dict[str, CodingBackendHealth]:
        results: dict[str, CodingBackendHealth] = {}
        for name in self._backends:
            results[name] = await self._probe_backend(name, timeout_seconds)
        return results

    async def _probe_backend(self, name: str, timeout_seconds: int) -> CodingBackendHealth:
        backend = self._backends[name]
        probe = getattr(backend, "probe_health", None)
        if callable(probe):
            return await probe(timeout_seconds)
        return CodingBackendHealth(backend=name, ready=True)

    async def execute(self, **kwargs: Any) -> ToolResultValue:
        agent_name = kwargs.pop("agent", None)
        if not isinstance(agent_name, str) or agent_name not in self._backends:
            available = ", ".join(self._backends.keys()) or "none"
            return f"Error: agent must be one of: {available}"

        health = await self._probe_backend(agent_name, timeout_seconds=20)
        if health is not None and not health.ready:
            return json.dumps(
                {
                    "status": "error",
                    "error_type": health.error_type or "backend_unavailable",
                    "summary": format_backend_issue(health) or f"{agent_name} backend unavailable",
                    "hints": list(health.hints),
                },
                ensure_ascii=False,
            )

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


CodingAgentDetailsTool = _CodingAgentDetailsTool
