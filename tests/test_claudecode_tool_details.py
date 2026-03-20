# ruff: noqa: F403, F405
from __future__ import annotations

from tests._claudecode_tool_testkit import *


def test_claudecode_details_fetches_by_request_id() -> None:
    with tempfile.TemporaryDirectory() as d:

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cmd, cwd, timeout_seconds
            return {
                "timed_out": False,
                "returncode": 0,
                "stdout": json.dumps({"result": "details out"}),
                "stderr": "warn",
            }

        tool = ClaudeCodeTool(workspace=Path(d))
        detail_tool = ClaudeCodeDetailsTool()
        tool.set_context("telegram", "bob")
        detail_tool.set_context("telegram", "bob")
        with patch(
            "bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/claude"
        ):
            with patch.object(ClaudeCodeTool, "_run_command", staticmethod(_fake_run)):
                payload_raw = _run(tool.execute(prompt="x", response_format="json"))

        payload = json.loads(payload_raw)
        details_raw = _run(
            detail_tool.execute(request_id=payload["request_id"], response_format="json")
        )

    details = json.loads(details_raw)
    assert details["stdout"] == json.dumps({"result": "details out"})
    assert details["stderr"] == "warn"


def test_claudecode_details_blocks_cross_context_request_id() -> None:
    with tempfile.TemporaryDirectory() as d:

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cmd, cwd, timeout_seconds
            return {
                "timed_out": False,
                "returncode": 0,
                "stdout": json.dumps({"result": "secret"}),
                "stderr": "",
            }

        tool = ClaudeCodeTool(workspace=Path(d))
        detail_tool = ClaudeCodeDetailsTool()
        tool.set_context("telegram", "alice")
        detail_tool.set_context("telegram", "alice")
        with patch(
            "bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/claude"
        ):
            with patch.object(ClaudeCodeTool, "_run_command", staticmethod(_fake_run)):
                payload_raw = _run(tool.execute(prompt="x", response_format="json"))

        request_id = json.loads(payload_raw)["request_id"]
        detail_tool.set_context("telegram", "bob")
        out = _run(detail_tool.execute(request_id=request_id, response_format="text"))

    assert "No Claude Code detail record found" in out
