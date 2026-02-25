import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from bao.agent.loop import AgentLoop
from bao.agent.tools.opencode import OpenCodeDetailsTool, OpenCodeTool
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


def test_opencode_tool_missing_binary() -> None:
    with tempfile.TemporaryDirectory() as d:
        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value=None):
            result = _run(tool.execute(prompt="hello"))
    assert "command not found" in result


def test_opencode_tool_rejects_path_outside_workspace() -> None:
    with tempfile.TemporaryDirectory() as d:
        workspace = Path(d)
        outside = workspace.parent
        tool = OpenCodeTool(workspace=workspace, allowed_dir=workspace)
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            result = _run(tool.execute(prompt="hello", project_path=str(outside)))
    assert "outside the allowed workspace" in result


def test_opencode_tool_success_sets_session_from_title() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cwd, timeout_seconds
            calls.append(cmd)
            return {"timed_out": False, "returncode": 0, "stdout": "done", "stderr": ""}

        async def _fake_resolve(
            self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int
        ) -> str | None:
            del self, cwd, title, timeout_seconds
            return "sess-123"

        tool = OpenCodeTool(workspace=Path(d))
        tool.set_context("telegram", "u1")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(_fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", _fake_resolve):
                    result = _run(tool.execute(prompt="Implement feature"))

    assert "OpenCode completed successfully" in result
    assert "Session: sess-123" in result
    assert calls and calls[0][0:2] == ["opencode", "run"]
    assert "--title" in calls[0]


def test_opencode_tool_continue_uses_chat_specific_session() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cwd, timeout_seconds
            calls.append(cmd)
            return {"timed_out": False, "returncode": 0, "stdout": "ok", "stderr": ""}

        async def _fake_resolve(
            self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int
        ) -> str | None:
            del self, cwd, title, timeout_seconds
            return "sess-a"

        tool = OpenCodeTool(workspace=Path(d))
        tool.set_context("telegram", "alice")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(_fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", _fake_resolve):
                    _run(tool.execute(prompt="first"))
                    calls.clear()
                    _run(tool.execute(prompt="second", continue_session=True))

    assert "--session" in calls[0]
    idx = calls[0].index("--session")
    assert calls[0][idx + 1] == "sess-a"


def test_opencode_tool_failure_returns_hints() -> None:
    with tempfile.TemporaryDirectory() as d:

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cmd, cwd, timeout_seconds
            return {
                "timed_out": False,
                "returncode": 2,
                "stdout": "permission ask",
                "stderr": "no providers",
            }

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(_fake_run)):
                result = _run(tool.execute(prompt="x"))

    assert "OpenCode failed" in result
    assert "opencode auth login" in result
    assert "permissions" in result.lower()


def test_opencode_tool_explicit_session_id_takes_priority() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cwd, timeout_seconds
            calls.append(cmd)
            return {"timed_out": False, "returncode": 0, "stdout": "ok", "stderr": ""}

        tool = OpenCodeTool(workspace=Path(d))
        tool.set_context("telegram", "alice")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(_fake_run)):
                _run(tool.execute(prompt="first", session_id="sess-explicit"))

    assert "--session" in calls[0]
    idx = calls[0].index("--session")
    assert calls[0][idx + 1] == "sess-explicit"
    assert "--title" not in calls[0]


def test_opencode_tool_continue_false_starts_new_session() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cwd, timeout_seconds
            calls.append(cmd)
            return {"timed_out": False, "returncode": 0, "stdout": "ok", "stderr": ""}

        async def _fake_resolve(
            self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int
        ) -> str | None:
            del self, cwd, title, timeout_seconds
            return "sess-a"

        tool = OpenCodeTool(workspace=Path(d))
        tool.set_context("telegram", "alice")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(_fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", _fake_resolve):
                    _run(tool.execute(prompt="first"))
                    calls.clear()
                    _run(tool.execute(prompt="second", continue_session=False))

    assert "--title" in calls[0]
    assert "--session" not in calls[0]


def test_opencode_tool_timeout_returns_actionable_error() -> None:
    with tempfile.TemporaryDirectory() as d:

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cmd, cwd, timeout_seconds
            return {"timed_out": True, "returncode": None, "stdout": "", "stderr": ""}

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(_fake_run)):
                result = _run(tool.execute(prompt="x", timeout_seconds=45))

    assert "timed out" in result
    assert "increase timeout_seconds" in result


def test_opencode_tool_json_response_contains_structured_fields() -> None:
    with tempfile.TemporaryDirectory() as d:

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cmd, cwd, timeout_seconds
            return {"timed_out": False, "returncode": 0, "stdout": "done", "stderr": ""}

        async def _fake_resolve(
            self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int
        ) -> str | None:
            del self, cwd, title, timeout_seconds
            return "sess-55"

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(_fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", _fake_resolve):
                    result = _run(tool.execute(prompt="x", response_format="json"))

    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["schema_version"] == 1
    assert isinstance(payload["request_id"], str) and payload["request_id"]
    assert payload["command_preview"].startswith("opencode run")
    assert payload["session_id"] == "sess-55"
    assert payload["attempts"] == 1
    assert payload["duration_ms"] >= 0
    assert payload["summary"] == "done"
    assert payload["stdout"] == ""
    assert payload["details_available"] is True


def test_opencode_tool_retries_transient_failure_once_by_default() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[int] = []

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cmd, cwd, timeout_seconds
            calls.append(1)
            if len(calls) == 1:
                return {
                    "timed_out": False,
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "rate limit",
                }
            return {"timed_out": False, "returncode": 0, "stdout": "ok", "stderr": ""}

        async def _fake_resolve(
            self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int
        ) -> str | None:
            del self, cwd, title, timeout_seconds
            return "sess-r"

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(_fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", _fake_resolve):
                    result = _run(tool.execute(prompt="x", response_format="json"))

    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["attempts"] == 2
    assert len(calls) == 2


def test_opencode_tool_rejects_invalid_timeout_type() -> None:
    with tempfile.TemporaryDirectory() as d:
        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            result = _run(tool.execute(prompt="x", timeout_seconds="120"))
    assert "timeout_seconds must be an integer" in result


def test_opencode_tool_hybrid_format_contains_meta_prefix() -> None:
    with tempfile.TemporaryDirectory() as d:

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cmd, cwd, timeout_seconds
            return {"timed_out": False, "returncode": 0, "stdout": "done", "stderr": ""}

        async def _fake_resolve(
            self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int
        ) -> str | None:
            del self, cwd, title, timeout_seconds
            return "sess-meta"

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(_fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", _fake_resolve):
                    result = _run(tool.execute(prompt="x", response_format="hybrid"))

    meta_lines = [line for line in result.splitlines() if line.startswith("OPENCODE_META=")]
    assert len(meta_lines) == 1
    meta = json.loads(meta_lines[0].split("=", 1)[1])
    assert meta["session_id"] == "sess-meta"
    assert meta["status"] == "success"


def test_opencode_tool_respects_max_output_chars() -> None:
    with tempfile.TemporaryDirectory() as d:
        long_text = "a" * 260

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cmd, cwd, timeout_seconds
            return {"timed_out": False, "returncode": 0, "stdout": long_text, "stderr": ""}

        async def _fake_resolve(
            self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int
        ) -> str | None:
            del self, cwd, title, timeout_seconds
            return "sess-limit"

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(_fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", _fake_resolve):
                    result = _run(
                        tool.execute(
                            prompt="x",
                            response_format="json",
                            max_output_chars=200,
                            include_details=True,
                        )
                    )

    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["stdout"].startswith("a" * 200)
    assert "truncated" in payload["stdout"]


def test_opencode_tool_include_details_returns_full_payload_output() -> None:
    with tempfile.TemporaryDirectory() as d:

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cmd, cwd, timeout_seconds
            return {"timed_out": False, "returncode": 0, "stdout": "done", "stderr": "warn"}

        async def _fake_resolve(
            self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int
        ) -> str | None:
            del self, cwd, title, timeout_seconds
            return "sess-details"

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(_fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", _fake_resolve):
                    result = _run(
                        tool.execute(prompt="x", response_format="json", include_details=True)
                    )

    payload = json.loads(result)
    assert payload["stdout"] == "done"
    assert payload["stderr"] == "warn"
    assert payload["details_hint"] is None


def test_opencode_tool_rejects_invalid_response_format() -> None:
    with tempfile.TemporaryDirectory() as d:
        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            result = _run(tool.execute(prompt="x", response_format="yaml"))
    assert "response_format must be one of" in result


def test_opencode_tool_rejects_invalid_max_output_chars_type() -> None:
    with tempfile.TemporaryDirectory() as d:
        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            result = _run(tool.execute(prompt="x", max_output_chars="400"))
    assert "max_output_chars must be an integer" in result


def test_agent_loop_registers_opencode_tool() -> None:
    with tempfile.TemporaryDirectory() as d:
        provider = _DummyProvider()
        with patch("bao.agent.loop.shutil.which", return_value="/usr/bin/opencode"):
            loop = AgentLoop(
                bus=MessageBus(),
                provider=provider,
                workspace=Path(d),
                model="dummy/model",
                max_iterations=2,
            )
    assert loop.tools.has("opencode")
    assert loop.tools.has("opencode_details")


def test_opencode_details_fetch_by_request_id() -> None:
    with tempfile.TemporaryDirectory() as d:

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cmd, cwd, timeout_seconds
            return {"timed_out": False, "returncode": 0, "stdout": "long details", "stderr": "warn"}

        async def _fake_resolve(
            self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int
        ) -> str | None:
            del self, cwd, title, timeout_seconds
            return "sess-details"

        tool = OpenCodeTool(workspace=Path(d))
        details_tool = OpenCodeDetailsTool()
        tool.set_context("telegram", "alice")
        details_tool.set_context("telegram", "alice")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(_fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", _fake_resolve):
                    payload_raw = _run(tool.execute(prompt="x", response_format="json"))
        payload = json.loads(payload_raw)
        detail_raw = _run(
            details_tool.execute(request_id=payload["request_id"], response_format="json")
        )
    detail = json.loads(detail_raw)
    assert detail["request_id"] == payload["request_id"]
    assert detail["stdout"] == "long details"
    assert detail["stderr"] == "warn"


def test_opencode_details_defaults_to_latest_context_record() -> None:
    with tempfile.TemporaryDirectory() as d:

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cmd, cwd, timeout_seconds
            return {"timed_out": False, "returncode": 0, "stdout": "context details", "stderr": ""}

        async def _fake_resolve(
            self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int
        ) -> str | None:
            del self, cwd, title, timeout_seconds
            return "sess-latest"

        tool = OpenCodeTool(workspace=Path(d))
        details_tool = OpenCodeDetailsTool()
        tool.set_context("telegram", "bob")
        details_tool.set_context("telegram", "bob")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(_fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", _fake_resolve):
                    _run(tool.execute(prompt="x", response_format="json"))
        out = _run(details_tool.execute(response_format="text"))
    assert "OpenCode details" in out
    assert "context details" in out


def test_opencode_details_blocks_cross_context_request_id() -> None:
    with tempfile.TemporaryDirectory() as d:

        async def _fake_run(cmd: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
            del cmd, cwd, timeout_seconds
            return {"timed_out": False, "returncode": 0, "stdout": "secret", "stderr": ""}

        async def _fake_resolve(
            self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int
        ) -> str | None:
            del self, cwd, title, timeout_seconds
            return "sess-isolated"

        tool = OpenCodeTool(workspace=Path(d))
        details_tool = OpenCodeDetailsTool()
        tool.set_context("telegram", "alice")
        details_tool.set_context("telegram", "alice")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(_fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", _fake_resolve):
                    payload_raw = _run(tool.execute(prompt="x", response_format="json"))
        request_id = json.loads(payload_raw)["request_id"]

        details_tool.set_context("telegram", "bob")
        out = _run(details_tool.execute(request_id=request_id, response_format="text"))

    assert "No OpenCode detail record found" in out
