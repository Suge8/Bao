from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from bao.agent.loop import AgentLoop
from bao.agent.tools.opencode import OpenCodeTool
from bao.bus.queue import MessageBus
from tests._opencode_tool_testkit import DummyProvider, make_run_result, run_async


def test_opencode_tool_missing_binary() -> None:
    with tempfile.TemporaryDirectory() as d:
        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value=None):
            result = run_async(tool.execute(prompt="hello"))
    assert "command not found" in result


def test_opencode_tool_rejects_path_outside_workspace() -> None:
    with tempfile.TemporaryDirectory() as d:
        workspace = Path(d)
        tool = OpenCodeTool(workspace=workspace, allowed_dir=workspace)
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            result = run_async(tool.execute(prompt="hello", project_path=str(workspace.parent)))
    assert "outside the allowed workspace" in result


def test_opencode_tool_resolves_short_agent_name_to_display_name() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []

        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cwd, timeout_seconds
            calls.append(cmd)
            if cmd[:3] == ["opencode", "debug", "config"]:
                return make_run_result(
                    {
                        "stdout": json.dumps(
                        {"agent": {"Hephaestus (Deep Agent)": {}, "Sisyphus (Ultraworker)": {}}}
                        )
                    }
                )
            return make_run_result({"stdout": "done"})

        async def fake_resolve(self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int):
            del self, cwd, title, timeout_seconds
            return "sess-agent"

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", fake_resolve):
                    result = run_async(
                        tool.execute(
                            prompt="Implement feature",
                            agent="Hephaestus",
                            response_format="json",
                        )
                    )

    payload = json.loads(result)
    run_calls = [cmd for cmd in calls if cmd[:3] != ["opencode", "debug", "config"]]
    assert payload["status"] == "success"
    assert calls[0][:3] == ["opencode", "debug", "config"]
    assert run_calls and "--agent" in run_calls[0]
    agent_idx = run_calls[0].index("--agent")
    assert run_calls[0][agent_idx + 1] == "Hephaestus (Deep Agent)"


def test_opencode_tool_keeps_short_name_when_alias_is_ambiguous() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []

        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cwd, timeout_seconds
            calls.append(cmd)
            if cmd[:3] == ["opencode", "debug", "config"]:
                return make_run_result(
                    {
                        "stdout": json.dumps(
                        {"agent": {"Explore (Primary)": {}, "Explore (Subagent)": {}}}
                        )
                    }
                )
            return make_run_result({"stdout": "done"})

        async def fake_resolve(self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int):
            del self, cwd, title, timeout_seconds
            return "sess-ambiguous"

        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", fake_resolve):
                    result = run_async(
                        tool.execute(prompt="Inspect", agent="Explore", response_format="json")
                    )

    payload = json.loads(result)
    run_calls = [cmd for cmd in calls if cmd[:3] != ["opencode", "debug", "config"]]
    assert payload["status"] == "success"
    assert run_calls and "--agent" in run_calls[0]
    agent_idx = run_calls[0].index("--agent")
    assert run_calls[0][agent_idx + 1] == "Explore"


def test_opencode_tool_rejects_invalid_timeout_type() -> None:
    with tempfile.TemporaryDirectory() as d:
        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            result = run_async(tool.execute(prompt="x", timeout_seconds="120"))
    assert "timeout_seconds must be an integer" in result


def test_opencode_tool_rejects_invalid_response_format() -> None:
    with tempfile.TemporaryDirectory() as d:
        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            result = run_async(tool.execute(prompt="x", response_format="yaml"))
    assert "response_format must be one of" in result


def test_opencode_tool_rejects_invalid_max_output_chars_type() -> None:
    with tempfile.TemporaryDirectory() as d:
        tool = OpenCodeTool(workspace=Path(d))
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            result = run_async(tool.execute(prompt="x", max_output_chars="400"))
    assert "max_output_chars must be an integer" in result


def test_agent_loop_registers_opencode_tool() -> None:
    with tempfile.TemporaryDirectory() as d:
        provider = DummyProvider()
        with patch("bao.agent.tools.coding_agent.shutil.which", return_value="/usr/bin/opencode"):
            loop = AgentLoop(
                bus=MessageBus(),
                provider=provider,
                workspace=Path(d),
                model="dummy/model",
                max_iterations=2,
            )
    assert loop.tools.has("coding_agent")
    assert loop.tools.has("coding_agent_details")
