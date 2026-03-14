"""Heartbeat service - periodic agent wake-up to check for tasks."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from loguru import logger

if TYPE_CHECKING:
    from bao.providers.base import LLMProvider

_HEARTBEAT_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "heartbeat",
            "description": "Report heartbeat decision after reviewing tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["skip", "run"],
                        "description": "skip = nothing to do, run = has active tasks",
                    },
                    "tasks": {
                        "type": "string",
                        "description": "Natural-language summary of active tasks (required for run)",
                    },
                },
                "required": ["action"],
            },
        },
    }
]


class HeartbeatService:
    """
    Periodic heartbeat service that wakes the agent to check for tasks.

    Phase 1 (decision): reads HEARTBEAT.md and asks the LLM — via a virtual
    tool call — whether there are active tasks.  This avoids free-text parsing
    and the unreliable HEARTBEAT_OK token.

    Phase 2 (execution): only triggered when Phase 1 returns ``run``.  The
    ``on_execute`` callback runs the task through the full agent loop and
    returns the result to deliver.
    """

    def __init__(
        self,
        workspace: Path,
        provider: LLMProvider,
        model: str,
        on_execute: Callable[[str], Coroutine[Any, Any, str]] | None = None,
        on_notify: Callable[[str], Coroutine[Any, Any, None]] | None = None,
        interval_s: int = 30 * 60,
        enabled: bool = True,
        service_tier: str | None = None,
    ):
        self.workspace = workspace
        self.provider = provider
        self.model = model
        self.on_execute = on_execute
        self.on_notify = on_notify
        self.interval_s = interval_s
        self.enabled = enabled
        self.service_tier = service_tier
        self._running = False
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._change_listeners: list[Callable[[], None]] = []
        self._last_checked_at_ms: int | None = None
        self._last_run_at_ms: int | None = None
        self._last_decision: str = ""
        self._last_error: str = ""

    def add_change_listener(self, listener: Callable[[], None]) -> None:
        if listener not in self._change_listeners:
            self._change_listeners.append(listener)

    def remove_change_listener(self, listener: Callable[[], None]) -> None:
        if listener in self._change_listeners:
            self._change_listeners.remove(listener)

    def _notify_changed(self) -> None:
        for listener in tuple(self._change_listeners):
            try:
                listener()
            except Exception as exc:
                logger.debug("Skip heartbeat change listener: {}", exc)

    def _now_ms(self) -> int:
        return int(datetime.now().timestamp() * 1000)

    @property
    def heartbeat_file(self) -> Path:
        return self.workspace / "HEARTBEAT.md"

    def _read_heartbeat_file(self) -> str | None:
        if self.heartbeat_file.exists():
            try:
                return self.heartbeat_file.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    async def _decide(self, content: str) -> tuple[str, str]:
        """Phase 1: ask LLM to decide skip/run via virtual tool call.

        Returns (action, tasks) where action is 'skip' or 'run'.
        """
        response = await self.provider.chat(
            messages=[
                {
                    "role": "system",
                    "content": "You are a heartbeat agent. Call the heartbeat tool to report your decision.",
                },
                {
                    "role": "user",
                    "content": (
                        "Review the following HEARTBEAT.md and decide whether there are active tasks.\n\n"
                        f"{content}"
                    ),
                },
            ],
            tools=_HEARTBEAT_TOOL,
            model=self.model,
            service_tier=self.service_tier,
        )

        if not response.has_tool_calls:
            return "skip", ""

        args = response.tool_calls[0].arguments
        return args.get("action", "skip"), args.get("tasks", "")

    async def start(self) -> None:
        """Start the heartbeat service."""
        if not self.enabled:
            logger.info("💓 心跳已禁用 / disabled")
            return
        if self._running:
            logger.warning("⚠️ 心跳已运行 / already running")
            return

        self._running = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        self._notify_changed()
        logger.info("💓 心跳已启动 / started ({}s)", self.interval_s)

    def stop(self) -> None:
        """Stop the heartbeat service."""
        self._running = False
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            self._task = None
        self._notify_changed()

    async def _run_loop(self) -> None:
        """Main heartbeat loop."""
        while self._running and not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_s)
            except asyncio.TimeoutError:
                if self._running and not self._stop_event.is_set():
                    await self.execute_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("❌ 心跳异常 / loop error: {}", e)

    async def execute_once(self, *, notify: bool = True) -> str | None:
        """Execute heartbeat decision once and optionally notify."""
        self._last_checked_at_ms = self._now_ms()
        self._last_error = ""
        self._notify_changed()
        content = self._read_heartbeat_file()
        if not content:
            logger.debug("💓 心跳文件缺失 / file missing: HEARTBEAT.md missing or empty")
            self._last_decision = "missing"
            self._notify_changed()
            return None

        logger.debug("💓 心跳检查任务 / checking tasks")

        try:
            action, tasks = await self._decide(content)
            self._last_decision = action

            if action != "run":
                logger.debug("💓 心跳无需上报 / nothing to report")
                self._notify_changed()
                return None

            logger.info("💓 心跳发现任务 / tasks found: executing")
            if self.on_execute:
                self._last_run_at_ms = self._now_ms()
                self._notify_changed()
                response = await self.on_execute(tasks)
                if response and notify and self.on_notify:
                    logger.info("💓 心跳执行完成 / completed: delivering response")
                    await self.on_notify(response)
                self._notify_changed()
                return response
        except Exception as exc:
            self._last_error = str(exc)
            logger.exception("❌ 心跳执行失败 / execution failed")
            self._notify_changed()
        return None

    async def trigger_now(self) -> str | None:
        """Manually trigger a heartbeat."""
        return await self.execute_once(notify=False)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "running": self._running,
            "interval_s": self.interval_s,
            "heartbeat_file": str(self.heartbeat_file),
            "heartbeat_file_exists": self.heartbeat_file.exists(),
            "last_checked_at_ms": self._last_checked_at_ms,
            "last_run_at_ms": self._last_run_at_ms,
            "last_decision": self._last_decision,
            "last_error": self._last_error,
        }
