from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from bao.agent.tools.opencode import OpenCodeTool
from tests._opencode_tool_testkit import make_run_result, run_async


def test_opencode_tool_failure_returns_hints() -> None:
    with tempfile.TemporaryDirectory() as d:
        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cmd, cwd, timeout_seconds
            return make_run_result(
                {"returncode": 2, "stdout": "permission ask", "stderr": "no providers"}
            )

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                result = run_async(tool.execute(prompt="x"))

    assert "OpenCode failed" in result
    assert "opencode auth login" in result
    assert "permissions" in result.lower()


def test_opencode_tool_timeout_returns_actionable_error() -> None:
    with tempfile.TemporaryDirectory() as d:
        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cmd, cwd, timeout_seconds
            return make_run_result({"timed_out": True, "returncode": None})

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                result = run_async(tool.execute(prompt="x", timeout_seconds=45))

    assert "timed out" in result
    assert "increase timeout_seconds" in result


def test_opencode_tool_timeout_at_max_avoids_increase_hint() -> None:
    with tempfile.TemporaryDirectory() as d:
        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cmd, cwd, timeout_seconds
            return make_run_result({"timed_out": True, "returncode": None})

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                result = run_async(tool.execute(prompt="x"))

    assert "timed out after 1800 seconds" in result
    assert "already at the 1800-second maximum" in result
    assert "increase timeout_seconds" not in result


def test_opencode_tool_json_response_contains_structured_fields() -> None:
    with tempfile.TemporaryDirectory() as d:
        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cmd, cwd, timeout_seconds
            return make_run_result({"stdout": "done"})

        async def fake_resolve(self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int):
            del self, cwd, title, timeout_seconds
            return "sess-55"

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", fake_resolve):
                    result = run_async(tool.execute(prompt="x", response_format="json"))

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


def test_opencode_tool_reports_transient_failure_without_hidden_retry() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[int] = []

        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cmd, cwd, timeout_seconds
            calls.append(1)
            return make_run_result({"returncode": 1, "stderr": "rate limit"})

        async def fake_resolve(self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int):
            del self, cwd, title, timeout_seconds
            return "sess-r"

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", fake_resolve):
                    result = run_async(tool.execute(prompt="x", response_format="json"))

    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["attempts"] == 1
    assert len(calls) == 1


def test_opencode_tool_hybrid_format_contains_meta_prefix() -> None:
    with tempfile.TemporaryDirectory() as d:
        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cmd, cwd, timeout_seconds
            return make_run_result({"stdout": "done"})

        async def fake_resolve(self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int):
            del self, cwd, title, timeout_seconds
            return "sess-meta"

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", fake_resolve):
                    result = run_async(tool.execute(prompt="x", response_format="hybrid"))

    meta_lines = [line for line in result.splitlines() if line.startswith("OPENCODE_META=")]
    meta = json.loads(meta_lines[0].split("=", 1)[1])
    assert len(meta_lines) == 1
    assert meta["session_id"] == "sess-meta"
    assert meta["status"] == "success"


def test_opencode_tool_respects_max_output_chars() -> None:
    with tempfile.TemporaryDirectory() as d:
        long_text = "a" * 260

        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cmd, cwd, timeout_seconds
            return make_run_result({"stdout": long_text})

        async def fake_resolve(self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int):
            del self, cwd, title, timeout_seconds
            return "sess-limit"

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", fake_resolve):
                    result = run_async(
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
        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cmd, cwd, timeout_seconds
            return make_run_result({"stdout": "done", "stderr": "warn"})

        async def fake_resolve(self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int):
            del self, cwd, title, timeout_seconds
            return "sess-details"

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", fake_resolve):
                    result = run_async(
                        tool.execute(prompt="x", response_format="json", include_details=True)
                    )

    payload = json.loads(result)
    assert payload["stdout"] == "done"
    assert payload["stderr"] == "warn"
    assert payload["details_hint"] is None
