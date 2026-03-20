"""Shared fixtures and helpers for subagent progress tests."""

import asyncio
import contextlib
import importlib
import tempfile
from pathlib import Path
from typing import Callable, Iterable
from unittest.mock import MagicMock

from bao.agent.loop import AgentLoop
from bao.agent.subagent import (
    RunRequest,
    SpawnResult,
    SubagentManager,
    SubagentManagerOptions,
    TaskStatus,
)
from bao.bus.events import ControlEvent, OutboundMessage
from bao.bus.queue import MessageBus

pytest = importlib.import_module("pytest")
pytestmark = [pytest.mark.integration, pytest.mark.slow]

DEFAULT_ORIGIN = {"channel": "tg", "chat_id": "1"}


def make_provider(model: str = "test-model") -> MagicMock:
    provider = MagicMock()
    provider.get_default_model.return_value = model
    return provider


def spawn_task_id(result: SpawnResult) -> str:
    assert result.task is not None
    return result.task.task_id


def subagent_options(tmp_path: Path, bus: MessageBus, **overrides) -> SubagentManagerOptions:
    payload = {"workspace": tmp_path, "bus": bus, "model": "test-model"}
    payload.update(overrides)
    return SubagentManagerOptions(**payload)


def add_task(manager: SubagentManager, **kwargs) -> TaskStatus:
    payload = {
        "task_id": "t1",
        "label": "task",
        "task_description": "d",
        "origin": DEFAULT_ORIGIN,
    }
    payload.update(kwargs)
    status = TaskStatus(
        task_id=payload.pop("task_id"),
        label=payload.pop("label"),
        task_description=payload.pop("task_description"),
        origin=payload.pop("origin"),
        **payload,
    )
    manager._task_statuses[status.task_id] = status
    return status


async def run_subagent_once(manager: SubagentManager, *, fake_chat: Callable, **kwargs):
    task_id = str(kwargs["task_id"])
    task = str(kwargs["task"])
    label = str(kwargs["label"])
    origin = dict(kwargs.get("origin") or DEFAULT_ORIGIN)
    task_kwargs = {key: value for key, value in kwargs.items() if key not in {"task_id", "task", "label", "origin"}}
    manager.provider.chat = fake_chat
    add_task(manager, task_id=task_id, label=label, task_description=task, origin=origin, **task_kwargs)
    await manager._run_subagent(
        RunRequest(
            task_id=task_id,
            task=task,
            label=label,
            origin=origin,
            context_from=task_kwargs.get("context_from"),
        )
    )
    return manager.get_task_status(task_id)


async def process_control_event(event: ControlEvent, **options) -> tuple[list[OutboundMessage], AgentLoop]:
    provider = make_provider()
    bus = MessageBus()

    async def _noop_mcp():
        pass

    workspace = options.get("workspace")
    ctx = (
        contextlib.nullcontext(workspace)
        if workspace is not None
        else tempfile.TemporaryDirectory()
    )
    with ctx as tmp:
        loop = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=Path(tmp),
            model="test-model",
        )

        captured: list[OutboundMessage] = []

        async def _capture(msg: OutboundMessage):
            captured.append(msg)

        loop.on_system_response = _capture
        if options.get("process_override") is not None:
            loop._process_control_event = options["process_override"]
        if options.get("run_agent_loop") is not None:
            loop._run_agent_loop = options["run_agent_loop"]
        if options.get("configure") is not None:
            options["configure"](loop)
        loop._connect_mcp = _noop_mcp

        loop._running = True
        run_task = asyncio.create_task(loop.run())
        await bus.publish_control(event)

        for _ in range(40):
            if captured or (
                bus.control_size == 0
                and bus.outbound_size > 0
                and not loop._session_runs._states
            ):
                break
            await asyncio.sleep(0.05)

        loop._running = False
        await asyncio.wait_for(run_task, timeout=2.0)

    return captured, loop


@pytest.fixture
def bus() -> MessageBus:
    return MessageBus()


@pytest.fixture
def manager(bus: MessageBus, tmp_path: Path) -> SubagentManager:
    provider = make_provider()
    return SubagentManager(
        provider,
        subagent_options(tmp_path, bus),
    )


def assert_in_text(needle: str, haystack: Iterable[str]) -> None:
    assert any(needle in item for item in haystack)
