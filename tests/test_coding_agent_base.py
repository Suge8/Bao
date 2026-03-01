import asyncio
import sys
import tempfile
import time
from pathlib import Path

from bao.agent.tools.coding_agent_base import BaseCodingAgentTool


def _run(coro):
    return asyncio.run(coro)


def test_run_command_timeout_returns_partial_output_and_exits_quickly() -> None:
    with tempfile.TemporaryDirectory() as d:
        cmd = [
            sys.executable,
            "-u",
            "-c",
            "import time; print('ready', flush=True); time.sleep(5)",
        ]

        started = time.monotonic()
        result = _run(BaseCodingAgentTool._run_command(cmd=cmd, cwd=Path(d), timeout_seconds=1))
        elapsed = time.monotonic() - started

    assert result["timed_out"] is True
    assert result["returncode"] is None
    assert "ready" in result["stdout"]
    assert elapsed < 4.5
