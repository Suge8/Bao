from __future__ import annotations

import gc
import pathlib
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from bao.bus.queue import MessageBus
from bao.utils.db import close_db

if TYPE_CHECKING:
    from bao.agent.loop import AgentLoop


@contextmanager
def workspace_dir() -> Iterator[pathlib.Path]:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        ws = pathlib.Path(td)
        (ws / "PERSONA.md").write_text("# Persona\n", encoding="utf-8")
        (ws / "INSTRUCTIONS.md").write_text("# Instructions\n", encoding="utf-8")
        try:
            yield ws
        finally:
            close_db(ws)
            gc.collect()
            shutil.rmtree(ws / "lancedb", ignore_errors=True)


@contextmanager
def loop_context(loop_bus: MessageBus, provider: MagicMock) -> Iterator["AgentLoop"]:
    with workspace_dir() as ws:
        from bao.agent.loop import AgentLoop

        loop = AgentLoop(bus=loop_bus, provider=provider, workspace=ws, model="test-model")
        try:
            yield loop
        finally:
            loop.close()
            del loop
            gc.collect()


def install_empty_memory(loop: "AgentLoop") -> None:
    loop.context.memory.search_memory = lambda query, limit=5: []
    loop.context.memory.search_experience = lambda query, limit=3: []
