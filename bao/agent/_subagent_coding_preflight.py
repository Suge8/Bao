from __future__ import annotations

from typing import Any

from bao.agent.tools._coding_agent_health import format_backend_issue

from ._subagent_types import RunRequest


class _SubagentCodingPreflightMixin:
    async def _resolve_coding_backends(
        self,
        *,
        request: RunRequest,
        coding_tool: Any,
        coding_tools: list[str],
    ) -> tuple[list[str], list[str]]:
        if not coding_tool or not coding_tools:
            return coding_tools, []
        collect_health = getattr(coding_tool, "collect_backend_health", None)
        if not callable(collect_health):
            return coding_tools, []
        health = await collect_health(timeout_seconds=20)
        healthy = [name for name in coding_tools if health.get(name) and health[name].ready]
        issues = [
            format_backend_issue(health[name])
            for name in coding_tools
            if health.get(name) and not health[name].ready
        ]
        requested = self._requested_coding_backend(request.task)
        if requested and requested in health and not health[requested].ready:
            detail = format_backend_issue(health[requested]) or f"{requested} backend unavailable"
            raise RuntimeError(f"Coding backend preflight failed: {detail}")
        return healthy, [item for item in issues if item]

    @staticmethod
    def _requested_coding_backend(task: str) -> str | None:
        lowered = task.lower()
        aliases = (
            ("codex", ("codex",)),
            ("opencode", ("opencode", "open code")),
            ("claudecode", ("claude code", "claudecode", "claude")),
        )
        for backend, names in aliases:
            if any(name in lowered for name in names):
                return backend
        return None
