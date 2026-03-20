from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from bao.agent.loop import AgentLoop
from bao.bus.queue import MessageBus


def make_loop(tmp_path: Path) -> AgentLoop:
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    with patch("bao.agent.loop.SubagentManager", return_value=MagicMock()):
        return AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path, model="test-model")
