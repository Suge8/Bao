import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from bao.agent.loop import AgentLoop
from bao.agent.tools.claudecode import ClaudeCodeDetailsTool, ClaudeCodeTool
from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse


class _DummyProvider(LLMProvider):
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        on_progress: Any = None,
        **kwargs: Any,
    ) -> LLMResponse:
        del messages, tools, model, max_tokens, temperature, on_progress, kwargs
        return LLMResponse(content="ok")

    def get_default_model(self) -> str:
        return "dummy/model"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


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


def test_claudecode_tool_continue_uses_context_session() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cwd, timeout_seconds
            calls.append(cmd)
            return {
                "timed_out": False,
                "returncode": 0,
                "stdout": json.dumps({"result": "ok", "session_id": "sess-real-a"}),
                "stderr": "",
            }

        tool = ClaudeCodeTool(workspace=Path(d))
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

        tool = ClaudeCodeTool(workspace=Path(d))
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


def test_agent_loop_registers_claudecode_tools() -> None:
    with tempfile.TemporaryDirectory() as d:
        provider = _DummyProvider()

        def _which(binary: str) -> str | None:
            return "/usr/bin/claude" if binary == "claude" else None

        with patch("bao.agent.loop.shutil.which", side_effect=_which):
            loop = AgentLoop(
                bus=MessageBus(),
                provider=provider,
                workspace=Path(d),
                model="dummy/model",
                max_iterations=2,
            )
    assert loop.tools.has("claudecode")
    assert loop.tools.has("claudecode_details")
