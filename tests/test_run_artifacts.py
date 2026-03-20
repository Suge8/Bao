from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from bao.agent._loop_run_models import RunAgentLoopOptions
from bao.agent.loop import AgentLoop
from bao.bus.queue import MessageBus
from bao.providers.base import LLMProvider, LLMResponse
from tests._provider_request_testkit import request_messages


class ArtifactProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(api_key=None, api_base=None)

    async def chat(self, request: Any, **kwargs: Any) -> LLMResponse:
        del kwargs
        _ = request_messages(request)
        return LLMResponse(content="done", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy/model"


def test_run_agent_loop_archives_run_artifact(tmp_path: Path) -> None:
    provider = ArtifactProvider()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        max_iterations=2,
    )
    loop._tool_exposure_mode = "off"

    final_content, _, _, _, _ = asyncio.run(
        loop._run_agent_loop(
            initial_messages=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "hello"},
            ],
            options=RunAgentLoopOptions(artifact_session_key="desktop:local"),
        )
    )

    assert final_content == "done"
    trajectory_dir = tmp_path / ".bao" / "context" / "desktop_local" / "trajectory"
    files = sorted(trajectory_dir.glob("agent_run_*.json"))
    assert files

    payload = json.loads(files[-1].read_text(encoding="utf-8"))
    assert payload["summary_strategy"]["prompt_summary_preserved"] is True
    assert payload["result"]["exit_reason"] == "completed"
    assert payload["result"]["provider_finish_reason"] == "stop"
    assert payload["tooling"]["tool_exposure_history"][0]["mode"] == "off"
    assert payload["tooling"]["tool_trace"] == []
