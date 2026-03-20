# ruff: noqa: F403, F405
from __future__ import annotations

from tests._claudecode_tool_testkit import *


def test_claudecode_tool_continue_uses_context_session() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []
        store = _FakeSessionStore()

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cwd, timeout_seconds
            calls.append(cmd)
            return {
                "timed_out": False,
                "returncode": 0,
                "stdout": json.dumps({"result": "ok", "session_id": "sess-real-a"}),
                "stderr": "",
            }

        tool = ClaudeCodeTool(workspace=Path(d), session_store=store)
        tool.set_context("telegram", "alice")
        with patch(
            "bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/claude"
        ):
            with patch.object(ClaudeCodeTool, "_run_command", staticmethod(_fake_run)):
                _run(tool.execute(prompt="first"))
                calls.clear()
                _run(tool.execute(prompt="second", continue_session=True))

    assert calls and "--resume" in calls[0]
    idx = calls[0].index("--resume")
    assert calls[0][idx + 1] == "sess-real-a"
    assert "--session-id" not in calls[0]
    assert store.sessions[("telegram:alice", "claudecode")] == "sess-real-a"


def test_claudecode_tool_explicit_session_id_takes_priority() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cwd, timeout_seconds
            calls.append(cmd)
            return {
                "timed_out": False,
                "returncode": 0,
                "stdout": json.dumps({"result": "ok", "session_id": "sess-canonical"}),
                "stderr": "",
            }

        tool = ClaudeCodeTool(workspace=Path(d))
        with patch(
            "bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/claude"
        ):
            with patch.object(ClaudeCodeTool, "_run_command", staticmethod(_fake_run)):
                _run(tool.execute(prompt="first", session_id="sess-explicit"))

    assert calls and "--resume" in calls[0]
    idx = calls[0].index("--resume")
    assert calls[0][idx + 1] == "sess-explicit"
    assert "--session-id" not in calls[0]


def test_claudecode_tool_continue_uses_canonical_session_from_stdout() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []
        store = _FakeSessionStore()

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cwd, timeout_seconds
            calls.append(cmd)
            if len(calls) == 1:
                return {
                    "timed_out": False,
                    "returncode": 0,
                    "stdout": json.dumps({"result": "ok", "session_id": "sess-canonical-1"}),
                    "stderr": "",
                }
            return {
                "timed_out": False,
                "returncode": 0,
                "stdout": json.dumps({"result": "ok2", "session_id": "sess-canonical-1"}),
                "stderr": "",
            }

        tool = ClaudeCodeTool(workspace=Path(d), session_store=store)
        tool.set_context("telegram", "alice")
        with patch(
            "bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/claude"
        ):
            with patch.object(ClaudeCodeTool, "_run_command", staticmethod(_fake_run)):
                _run(tool.execute(prompt="first", session_id="named-session"))
                calls.clear()
                _run(tool.execute(prompt="second", continue_session=True))

    assert calls and "--resume" in calls[0]
    idx = calls[0].index("--resume")
    assert calls[0][idx + 1] == "sess-canonical-1"
    assert store.sessions[("telegram:alice", "claudecode")] == "sess-canonical-1"


def test_claudecode_tool_clears_stale_stored_session_without_hidden_retry() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []
        store = _FakeSessionStore()
        store.sessions[("telegram:alice", "claudecode")] = "sess-stale"

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cwd, timeout_seconds
            calls.append(cmd)
            return {
                "timed_out": False,
                "returncode": 1,
                "stdout": "",
                "stderr": "session not found",
            }

        tool = ClaudeCodeTool(workspace=Path(d), session_store=store)
        tool.set_context("telegram", "alice")
        with patch(
            "bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/claude"
        ):
            with patch.object(ClaudeCodeTool, "_run_command", staticmethod(_fake_run)):
                result = _run(tool.execute(prompt="retry stale", response_format="json"))

    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["error_type"] == "stale_session"
    assert len(calls) == 1
    assert "--resume" in calls[0]
    idx = calls[0].index("--resume")
    assert calls[0][idx + 1] == "sess-stale"
    assert ("telegram:alice", "claudecode") not in store.sessions
