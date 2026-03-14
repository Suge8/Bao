import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bao.agent.loop import AgentLoop
from bao.agent.tools.agent_browser import AgentBrowserRunner, AgentBrowserTool
from bao.browser import SUPPORTED_BROWSER_ACTIONS, current_browser_platform_key
from bao.bus.queue import MessageBus
from bao.config.paths import set_runtime_config_path
from bao.providers.base import LLMProvider, LLMResponse
from tests.browser_runtime_fixture import write_fake_browser_runtime


class _DummyProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(api_key=None, api_base=None)

    async def chat(
        self,
        messages,
        tools=None,
        model=None,
        max_tokens=4096,
        temperature=0.7,
        on_progress=None,
        **kwargs,
    ):
        del messages, tools, model, max_tokens, temperature, on_progress, kwargs
        return LLMResponse(content="ok", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy/model"


def test_agent_browser_tool_reports_missing_runtime(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BAO_BROWSER_RUNTIME_ROOT", str(tmp_path / "missing-runtime"))
    set_runtime_config_path(tmp_path / "config.jsonc")
    try:
        tool = AgentBrowserTool(workspace=tmp_path)
        result = asyncio.run(tool.execute(action="open", args=["https://example.com"]))
    finally:
        set_runtime_config_path(None)
    assert "managed browser runtime is not ready" in result


def test_agent_browser_tool_schema_uses_runtime_action_source() -> None:
    tool = AgentBrowserTool(workspace=Path.cwd())

    assert tool.parameters["properties"]["action"]["enum"] == list(SUPPORTED_BROWSER_ACTIONS)


def test_agent_browser_runner_builds_command_with_context_and_flags(
    tmp_path: Path, monkeypatch
) -> None:
    runtime_root = write_fake_browser_runtime(tmp_path)
    platform_key = current_browser_platform_key()
    agent_binary = "agent-browser.exe" if platform_key.startswith("win32-") else "agent-browser"
    browser_binary = "chrome.exe" if platform_key.startswith("win32-") else "chrome"
    monkeypatch.setenv("BAO_BROWSER_RUNTIME_ROOT", str(runtime_root))
    set_runtime_config_path(tmp_path / "config.jsonc")
    try:
        runner = AgentBrowserRunner(workspace=tmp_path)
        runner.set_context("telegram", "alice", session_key="sess/one")
        with patch.object(
            runner._service,
            "_run_command",
            new=AsyncMock(return_value="ok"),
        ) as run_command:
            out = asyncio.run(
                runner.run(
                    action="open",
                    args=["https://example.com"],
                    headed=True,
                    proxy="http://localhost:7890",
                )
            )
    finally:
        set_runtime_config_path(None)

    assert out == "ok"
    command = run_command.await_args.args[0]
    assert command[0] == str(runtime_root / "platforms" / platform_key / "bin" / agent_binary)
    assert command[1:5] == [
        "--profile",
        str(tmp_path / "browser" / "profile"),
        "--executable-path",
        str(runtime_root / "platforms" / platform_key / "browser" / browser_binary),
    ]
    assert "--session" in command
    assert "sess-one" in command
    assert "--headed" in command
    assert "--json" in command
    assert command[-2:] == ["open", "https://example.com"]


def test_agent_browser_runner_rejects_paths_outside_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    runtime_root = write_fake_browser_runtime(tmp_path)
    monkeypatch.setenv("BAO_BROWSER_RUNTIME_ROOT", str(runtime_root))
    set_runtime_config_path(tmp_path / "config.jsonc")
    try:
        runner = AgentBrowserRunner(workspace=tmp_path, allowed_dir=tmp_path)
        result = asyncio.run(
            runner.run(
                action="screenshot",
                args=["/tmp/outside.png"],
            )
        )
    finally:
        set_runtime_config_path(None)
    assert "must stay within the workspace" in result


def test_agent_loop_registers_agent_browser_when_runtime_is_ready(
    tmp_path: Path, monkeypatch
) -> None:
    runtime_root = write_fake_browser_runtime(tmp_path)
    monkeypatch.setenv("BAO_BROWSER_RUNTIME_ROOT", str(runtime_root))
    set_runtime_config_path(tmp_path / "config.jsonc")
    try:
        loop = AgentLoop(bus=MessageBus(), provider=_DummyProvider(), workspace=tmp_path)
    finally:
        set_runtime_config_path(None)
    assert loop.tools.has("agent_browser")


def test_agent_loop_keeps_agent_browser_registered_when_runtime_missing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("BAO_BROWSER_RUNTIME_ROOT", str(tmp_path / "missing-runtime"))
    set_runtime_config_path(tmp_path / "config.jsonc")
    try:
        loop = AgentLoop(bus=MessageBus(), provider=_DummyProvider(), workspace=tmp_path)
    finally:
        set_runtime_config_path(None)

    assert loop.tools.has("agent_browser")
