# ruff: noqa: F403, F405
from __future__ import annotations

from tests._claudecode_tool_testkit import *


def test_claudecode_tool_missing_binary() -> None:
    with tempfile.TemporaryDirectory() as d:
        tool = ClaudeCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value=None):
            result = _run(tool.execute(prompt="hello"))
    assert "command not found" in result


def test_claudecode_tool_success_with_generated_session() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cwd, timeout_seconds
            calls.append(cmd)
            return {
                "timed_out": False,
                "returncode": 0,
                "stdout": json.dumps({"result": "done", "session_id": "sess-real-1"}),
                "stderr": "",
            }

        tool = ClaudeCodeTool(workspace=Path(d))
        tool.set_context("telegram", "alice")
        with patch(
            "bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/claude"
        ):
            with patch.object(ClaudeCodeTool, "_run_command", staticmethod(_fake_run)):
                result = _run(tool.execute(prompt="Implement", response_format="json"))

    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["summary"] == "done"
    assert payload["session_id"] == "sess-real-1"
    assert calls and calls[0][0:4] == ["claude", "-p", "--output-format", "json"]
    assert "--session-id" in calls[0]


def test_claudecode_tool_uses_result_from_previous_json_object() -> None:
    with tempfile.TemporaryDirectory() as d:

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cmd, cwd, timeout_seconds
            stdout = "\n".join(
                [
                    json.dumps({"result": "primary-result", "session_id": "sess-jsonl-1"}),
                    json.dumps({"type": "completion", "session_id": "sess-jsonl-1"}),
                ]
            )
            return {
                "timed_out": False,
                "returncode": 0,
                "stdout": stdout,
                "stderr": "",
            }

        tool = ClaudeCodeTool(workspace=Path(d))
        with patch(
            "bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/claude"
        ):
            with patch.object(ClaudeCodeTool, "_run_command", staticmethod(_fake_run)):
                result = _run(tool.execute(prompt="jsonl", response_format="json"))

    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["summary"] == "primary-result"
    assert payload["session_id"] == "sess-jsonl-1"


def test_agent_loop_registers_claudecode_tools() -> None:
    with tempfile.TemporaryDirectory() as d:
        provider = _DummyProvider()

        def _which(binary: str) -> str | None:
            return "/usr/bin/claude" if binary == "claude" else None

        with patch("bao.agent.tools.coding_agent.shutil.which", side_effect=_which):
            loop = AgentLoop(
                bus=MessageBus(),
                provider=provider,
                workspace=Path(d),
                model="dummy/model",
                max_iterations=2,
            )
    assert loop.tools.has("coding_agent")
    assert loop.tools.has("coding_agent_details")
