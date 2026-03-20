from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from bao.agent.tools.opencode import OpenCodeTool
from tests._opencode_tool_testkit import FakeSessionStore, make_run_result, run_async


def test_opencode_tool_success_sets_session_from_title() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []

        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cwd, timeout_seconds
            calls.append(cmd)
            return make_run_result({"stdout": "done"})

        async def fake_resolve(self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int):
            del self, cwd, title, timeout_seconds
            return "sess-123"

        tool = OpenCodeTool(workspace=Path(d))
        tool.set_context("telegram", "u1")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", fake_resolve):
                    result = run_async(tool.execute(prompt="Implement feature"))

    assert "OpenCode completed successfully" in result
    assert "Session: sess-123" in result
    assert calls and calls[0][0:2] == ["opencode", "run"]
    assert "--title" in calls[0]


def test_opencode_tool_continue_uses_chat_specific_session() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []
        store = FakeSessionStore()

        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cwd, timeout_seconds
            calls.append(cmd)
            return make_run_result({"stdout": "ok"})

        async def fake_resolve(self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int):
            del self, cwd, title, timeout_seconds
            return "sess-a"

        tool = OpenCodeTool(workspace=Path(d), session_store=store)
        tool.set_context("telegram", "alice")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", fake_resolve):
                    run_async(tool.execute(prompt="first"))
                    calls.clear()
                    run_async(tool.execute(prompt="second", continue_session=True))

    idx = calls[0].index("--session")
    assert "--session" in calls[0]
    assert calls[0][idx + 1] == "sess-a"
    assert store.sessions[("telegram:alice", "opencode")] == "sess-a"


def test_opencode_tool_explicit_session_id_takes_priority() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []

        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cwd, timeout_seconds
            calls.append(cmd)
            return make_run_result({"stdout": "ok"})

        tool = OpenCodeTool(workspace=Path(d))
        tool.set_context("telegram", "alice")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                run_async(tool.execute(prompt="first", session_id="sess-explicit"))

    idx = calls[0].index("--session")
    assert calls[0][idx + 1] == "sess-explicit"
    assert "--title" not in calls[0]


def test_opencode_tool_continue_false_starts_new_session() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []

        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cwd, timeout_seconds
            calls.append(cmd)
            return make_run_result({"stdout": "ok"})

        async def fake_resolve(self: OpenCodeTool, cwd: Path, title: str, timeout_seconds: int):
            del self, cwd, title, timeout_seconds
            return "sess-a"

        tool = OpenCodeTool(workspace=Path(d))
        tool.set_context("telegram", "alice")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                with patch.object(OpenCodeTool, "_resolve_session_by_title", fake_resolve):
                    run_async(tool.execute(prompt="first"))
                    calls.clear()
                    run_async(tool.execute(prompt="second", continue_session=False))

    assert "--title" in calls[0]
    assert "--session" not in calls[0]


def test_opencode_tool_persists_sessions_per_context_via_store() -> None:
    with tempfile.TemporaryDirectory() as d:
        store = FakeSessionStore()

        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cmd, cwd, timeout_seconds
            return make_run_result({"stdout": "ok"})

        async def fake_resolve_after_success(*args: object, **kwargs: object):
            del kwargs
            self = args[0]
            return f"sess-{self._context_key.get()}"

        tool = OpenCodeTool(workspace=Path(d), session_store=store)
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                with patch.object(
                    OpenCodeTool,
                    "_resolve_session_after_success",
                    fake_resolve_after_success,
                ):
                    tool.set_context("telegram", "alice")
                    run_async(tool.execute(prompt="alice-1"))
                    tool.set_context("telegram", "bob")
                    run_async(tool.execute(prompt="bob-1"))
                    tool.set_context("telegram", "carol")
                    run_async(tool.execute(prompt="carol-1"))

    assert store.sessions == {
        ("telegram:alice", "opencode"): "sess-telegram:alice",
        ("telegram:bob", "opencode"): "sess-telegram:bob",
        ("telegram:carol", "opencode"): "sess-telegram:carol",
    }


def test_opencode_tool_clears_stale_stored_session_without_hidden_retry() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []
        store = FakeSessionStore()
        store.sessions[("telegram:alice", "opencode")] = "sess-stale"

        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cwd, timeout_seconds
            calls.append(cmd)
            return make_run_result({"returncode": 1, "stderr": "session not found"})

        tool = OpenCodeTool(workspace=Path(d), session_store=store)
        tool.set_context("telegram", "alice")
        with patch("bao.agent.tools.coding_agent_base.shutil.which", return_value="/usr/bin/opencode"):
            with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
                result = run_async(tool.execute(prompt="retry stale", response_format="json"))

    payload = json.loads(result)
    stale_idx = calls[0].index("--session")
    assert payload["status"] == "error"
    assert payload["error_type"] == "stale_session"
    assert payload["attempts"] == 1
    assert calls[0][stale_idx + 1] == "sess-stale"
    assert ("telegram:alice", "opencode") not in store.sessions


def test_opencode_tool_resolve_session_by_title_falls_back_to_larger_window() -> None:
    with tempfile.TemporaryDirectory() as d:
        calls: list[list[str]] = []

        async def fake_run(cmd: list[str], cwd: Path, timeout_seconds: int):
            del cwd, timeout_seconds
            calls.append(cmd)
            sessions = [{"id": "sess-old", "title": "other-title"}]
            if cmd[-1] != "20":
                sessions = [{"id": "sess-target", "title": "target-title"}]
            return make_run_result({"stdout": json.dumps(sessions)})

        tool = OpenCodeTool(workspace=Path(d))
        with patch.object(OpenCodeTool, "_run_command", staticmethod(fake_run)):
            session_id = run_async(tool._resolve_session_by_title(Path(d), "target-title", 30))

    assert session_id == "sess-target"
    assert len(calls) == 2
    assert calls[0][-1] == "20"
    assert calls[1][-1] == "100"
