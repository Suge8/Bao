from __future__ import annotations

from pathlib import Path
from typing import Any

from bao.agent.tools.base import Tool
from bao.browser import (
    SUPPORTED_BROWSER_ACTIONS,
    BrowserAutomationService,
    get_browser_capability_state,
)


def agent_browser_available(*, enabled: bool = True) -> bool:
    return get_browser_capability_state(enabled=enabled).available


class AgentBrowserRunner:
    def __init__(
        self,
        *,
        workspace: Path,
        enabled: bool = True,
        allowed_dir: Path | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self._service = BrowserAutomationService(
            workspace=workspace,
            enabled=enabled,
            allowed_dir=allowed_dir,
            timeout_seconds=timeout_seconds,
        )

    @property
    def available(self) -> bool:
        return self._service.available

    @property
    def state(self):
        return self._service.state

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        self._service.set_context(channel, chat_id, session_key)

    @staticmethod
    def normalize_session(value: str) -> str:
        return BrowserAutomationService.normalize_session(value)

    async def run(self, *, action: str, args: list[str] | None = None, **options: Any) -> str:
        return await self._service.run(
            action=action,
            args=args if isinstance(args, list) else [],
            **options,
        )

    async def fetch_html(
        self, url: str, *, wait_ms: int = 1500, session: str | None = None
    ) -> dict[str, str]:
        return await self._service.fetch_html(url, wait_ms=wait_ms, session=session)


class AgentBrowserTool(Tool):
    def __init__(
        self,
        *,
        workspace: Path,
        enabled: bool = True,
        allowed_dir: Path | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self._runner = AgentBrowserRunner(
            workspace=workspace,
            enabled=enabled,
            allowed_dir=allowed_dir,
            timeout_seconds=timeout_seconds,
        )

    @property
    def available(self) -> bool:
        return self._runner.available

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        self._runner.set_context(channel, chat_id, session_key)

    @property
    def name(self) -> str:
        return "agent_browser"

    @property
    def description(self) -> str:
        return "Control Bao's managed browser for interactive pages, forms, screenshots, and DOM inspection."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": list(SUPPORTED_BROWSER_ACTIONS)},
                "args": {"type": "array", "items": {"type": "string"}},
                "session": {"type": "string"},
                "headed": {"type": "boolean"},
                "fullPage": {"type": "boolean"},
                "annotate": {"type": "boolean"},
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        args = kwargs.get("args")
        if not isinstance(action, str):
            return "Error: Missing required parameter 'action'"
        options = {
            "session": kwargs.get("session"),
            "headed": kwargs.get("headed"),
            "full_page": kwargs.get("fullPage"),
            "annotate": kwargs.get("annotate"),
        }
        return await self._runner.run(
            action=action,
            args=args if isinstance(args, list) else [],
            **options,
        )
