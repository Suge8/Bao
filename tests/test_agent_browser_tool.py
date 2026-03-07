import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bao.agent.loop import AgentLoop
from bao.agent.tools.agent_browser import AgentBrowserRunner, AgentBrowserTool
from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse


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


def test_agent_browser_tool_reports_missing_binary(tmp_path: Path) -> None:
    tool = AgentBrowserTool(workspace=tmp_path)
    with patch("bao.agent.tools.agent_browser.shutil.which", return_value=None):
        result = asyncio.run(tool.execute(action="open", args=["https://example.com"]))
    assert "not installed" in result


def test_agent_browser_runner_builds_command_with_context_and_flags(tmp_path: Path) -> None:
    runner = AgentBrowserRunner(workspace=tmp_path)
    runner.set_context("telegram", "alice", session_key="sess/one")

    with patch("bao.agent.tools.agent_browser.shutil.which", return_value="/usr/bin/agent-browser"):
        with patch.object(runner, "_run_command", new=AsyncMock(return_value="ok")) as run_command:
            out = asyncio.run(
                runner.run(
                    action="open",
                    args=["https://example.com"],
                    headed=True,
                    proxy="http://localhost:7890",
                )
            )

    assert out == "ok"
    command = run_command.await_args.args[0]
    assert command[:4] == ["/usr/bin/agent-browser", "--session", "sess-one", "--proxy"]
    assert "--headed" in command
    assert "--json" in command
    assert command[-2:] == ["open", "https://example.com"]


def test_agent_browser_runner_rejects_paths_outside_workspace(tmp_path: Path) -> None:
    runner = AgentBrowserRunner(workspace=tmp_path, allowed_dir=tmp_path)
    with patch("bao.agent.tools.agent_browser.shutil.which", return_value="/usr/bin/agent-browser"):
        result = asyncio.run(
            runner.run(
                action="screenshot",
                args=["/tmp/outside.png"],
            )
        )
    assert "must stay within the workspace" in result


def test_agent_loop_registers_agent_browser_when_available(tmp_path: Path) -> None:
    with patch("bao.agent.tools.agent_browser.shutil.which", return_value="/usr/bin/agent-browser"):
        loop = AgentLoop(bus=MessageBus(), provider=_DummyProvider(), workspace=tmp_path)
    assert loop.tools.has("agent_browser")
