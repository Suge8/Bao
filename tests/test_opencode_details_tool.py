from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from bao.agent.tools.opencode import OpenCodeDetailsTool, OpenCodeTool
from tests._opencode_tool_testkit import make_run_result, run_async


def test_opencode_details_fetch_by_request_id() -> None:
    with tempfile.TemporaryDirectory() as d:
        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cmd, cwd, timeout_seconds
            return make_run_result({"stdout": "long details", "stderr": "warn"})

        async def fake_resolve(self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int):
            del self, cwd, title, timeout_seconds
            return "sess-details"

        tool = OpenCodeTool(workspace=Path(d))
        details_tool = OpenCodeDetailsTool()
        tool.set_context("telegram", "alice")
        details_tool.set_context("telegram", "alice")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", fake_resolve):
                    payload_raw = run_async(tool.execute(prompt="x", response_format="json"))
        request_id = json.loads(payload_raw)["request_id"]
        detail_raw = run_async(details_tool.execute(request_id=request_id, response_format="json"))

    detail = json.loads(detail_raw)
    assert detail["request_id"] == request_id
    assert detail["stdout"] == "long details"
    assert detail["stderr"] == "warn"


def test_opencode_details_defaults_to_latest_context_record() -> None:
    with tempfile.TemporaryDirectory() as d:
        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cmd, cwd, timeout_seconds
            return make_run_result({"stdout": "context details"})

        async def fake_resolve(self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int):
            del self, cwd, title, timeout_seconds
            return "sess-latest"

        tool = OpenCodeTool(workspace=Path(d))
        details_tool = OpenCodeDetailsTool()
        tool.set_context("telegram", "bob")
        details_tool.set_context("telegram", "bob")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", fake_resolve):
                    run_async(tool.execute(prompt="x", response_format="json"))
        out = run_async(details_tool.execute(response_format="text"))

    assert "OpenCode details" in out
    assert "context details" in out


def test_opencode_details_blocks_cross_context_request_id() -> None:
    with tempfile.TemporaryDirectory() as d:
        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cmd, cwd, timeout_seconds
            return make_run_result({"stdout": "secret"})

        async def fake_resolve(self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int):
            del self, cwd, title, timeout_seconds
            return "sess-isolated"

        tool = OpenCodeTool(workspace=Path(d))
        details_tool = OpenCodeDetailsTool()
        tool.set_context("telegram", "alice")
        details_tool.set_context("telegram", "alice")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", fake_resolve):
                    payload_raw = run_async(tool.execute(prompt="x", response_format="json"))

        request_id = json.loads(payload_raw)["request_id"]
        details_tool.set_context("telegram", "bob")
        out = run_async(details_tool.execute(request_id=request_id, response_format="text"))

    assert "No OpenCode detail record found" in out
