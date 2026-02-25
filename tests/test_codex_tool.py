import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from bao.agent.loop import AgentLoop
from bao.agent.tools.codex import CodexDetailsTool, CodexTool
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


def test_codex_tool_missing_binary() -> None:
    with tempfile.TemporaryDirectory() as d:
        tool = CodexTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value=None):
            result = _run(tool.execute(prompt="hello"))
    assert "command not found" in result


def test_codex_tool_rejects_invalid_sandbox() -> None:
    with tempfile.TemporaryDirectory() as d:
        tool = CodexTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/codex"):
            result = _run(tool.execute(prompt="x", sandbox="unsafe"))
    assert "sandbox must be one of" in result


def test_codex_tool_parses_session_and_summary_from_jsonl_and_file() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []
        output_text = "final from file"

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cwd, timeout_seconds
            calls.append(cmd)
            out_idx = cmd.index("-o") + 1
            out_file = Path(cmd[out_idx])
            out_file.write_text(output_text, encoding="utf-8")
            stdout = json.dumps({"event": "done", "session_id": "sess-cx-1"}) + "\n"
            return {"timed_out": False, "returncode": 0, "stdout": stdout, "stderr": ""}

        tool = CodexTool(workspace=Path(d))
        tool.set_context("telegram", "alice")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/codex"):
            with patch.object(CodexTool, "_run_command", staticmethod(_fake_run)):
                result = _run(tool.execute(prompt="Implement", response_format="json"))

    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["session_id"] == "sess-cx-1"
    assert payload["summary"] == "final from file"
    assert payload["stdout"] == ""
    assert calls and calls[0][0:2] == ["codex", "exec"]
    assert "--full-auto" not in calls[0]


def test_codex_tool_full_auto_enabled_explicitly() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cwd, timeout_seconds
            calls.append(cmd)
            out_idx = cmd.index("-o") + 1
            Path(cmd[out_idx]).write_text("ok", encoding="utf-8")
            return {"timed_out": False, "returncode": 0, "stdout": "", "stderr": ""}

        tool = CodexTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/codex"):
            with patch.object(CodexTool, "_run_command", staticmethod(_fake_run)):
                _run(tool.execute(prompt="Implement", full_auto=True))

    assert calls and "--full-auto" in calls[0]


def test_codex_tool_continue_uses_context_session() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cwd, timeout_seconds
            calls.append(cmd)
            out_idx = cmd.index("-o") + 1
            Path(cmd[out_idx]).write_text("ok", encoding="utf-8")
            if len(calls) == 1:
                stdout = json.dumps({"session_id": "sess-cx-a", "message": "ok"})
            else:
                stdout = json.dumps({"message": "ok2"})
            return {"timed_out": False, "returncode": 0, "stdout": stdout, "stderr": ""}

        tool = CodexTool(workspace=Path(d))
        tool.set_context("telegram", "alice")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/codex"):
            with patch.object(CodexTool, "_run_command", staticmethod(_fake_run)):
                _run(tool.execute(prompt="first"))
                calls.clear()
                _run(tool.execute(prompt="second", continue_session=True))

    assert calls and calls[0][0:3] == ["codex", "exec", "resume"]
    assert "sess-cx-a" in calls[0]


def test_codex_details_fetches_by_request_id() -> None:
    with tempfile.TemporaryDirectory() as d:

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cwd, timeout_seconds
            out_idx = cmd.index("-o") + 1
            Path(cmd[out_idx]).write_text("details out", encoding="utf-8")
            stdout = json.dumps({"session_id": "sess-cx-d", "message": "done"})
            return {"timed_out": False, "returncode": 0, "stdout": stdout, "stderr": "warn"}

        tool = CodexTool(workspace=Path(d))
        detail_tool = CodexDetailsTool()
        tool.set_context("telegram", "bob")
        detail_tool.set_context("telegram", "bob")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/codex"):
            with patch.object(CodexTool, "_run_command", staticmethod(_fake_run)):
                payload_raw = _run(tool.execute(prompt="x", response_format="json"))

        payload = json.loads(payload_raw)
        details_raw = _run(
            detail_tool.execute(request_id=payload["request_id"], response_format="json")
        )

    details = json.loads(details_raw)
    assert details["stdout"] == "details out"
    assert details["stderr"] == "warn"


def test_codex_details_blocks_cross_context_request_id() -> None:
    with tempfile.TemporaryDirectory() as d:

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cwd, timeout_seconds
            out_idx = cmd.index("-o") + 1
            Path(cmd[out_idx]).write_text("secret", encoding="utf-8")
            stdout = json.dumps({"session_id": "sess-cx-x", "message": "done"})
            return {"timed_out": False, "returncode": 0, "stdout": stdout, "stderr": ""}

        tool = CodexTool(workspace=Path(d))
        detail_tool = CodexDetailsTool()
        tool.set_context("telegram", "alice")
        detail_tool.set_context("telegram", "alice")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/codex"):
            with patch.object(CodexTool, "_run_command", staticmethod(_fake_run)):
                payload_raw = _run(tool.execute(prompt="x", response_format="json"))

        request_id = json.loads(payload_raw)["request_id"]
        detail_tool.set_context("telegram", "bob")
        out = _run(detail_tool.execute(request_id=request_id, response_format="text"))

    assert "No Codex detail record found" in out


def test_agent_loop_registers_codex_tools() -> None:
    with tempfile.TemporaryDirectory() as d:
        provider = _DummyProvider()
        with patch("bao.agent.loop.shutil.which", return_value="/usr/bin/codex"):
            loop = AgentLoop(
                bus=MessageBus(),
                provider=provider,
                workspace=Path(d),
                model="dummy/model",
                max_iterations=2,
            )
    assert loop.tools.has("codex")
    assert loop.tools.has("codex_details")
