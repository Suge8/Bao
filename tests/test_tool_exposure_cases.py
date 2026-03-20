from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from bao.agent.loop import AgentLoop
from bao.agent.tool_exposure_eval import DEFAULT_TOOL_EXPOSURE_CASES_PATH, load_tool_exposure_cases
from bao.bus.queue import MessageBus
from bao.config.schema import Config, ToolExposureConfig, ToolsConfig
from bao.providers.base import LLMProvider, LLMResponse
from tests._provider_request_testkit import request_messages


class DummyProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(api_key=None, api_base=None)

    async def chat(self, request: Any, **kwargs: Any) -> LLMResponse:
        del kwargs
        _ = request_messages(request)
        return LLMResponse(content="ok", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy/model"


def _load_cases() -> list[dict[str, Any]]:
    return load_tool_exposure_cases(DEFAULT_TOOL_EXPOSURE_CASES_PATH)


def _make_loop(tmp_path: Path, *, mode: str, domains: list[str], monkeypatch: pytest.MonkeyPatch) -> AgentLoop:
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    cfg = Config(tools=ToolsConfig(tool_exposure=ToolExposureConfig(mode=mode, domains=domains)))
    return AgentLoop(bus=MessageBus(), provider=DummyProvider(), workspace=tmp_path, config=cfg)


def test_tool_exposure_cases_match_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for case in _load_cases():
        mode = str(case.get("expected_mode") or "auto")
        domains = list(
            case.get("run_with_domains")
            or [
                "core",
                "messaging",
                "handoff",
                "web_research",
                "desktop_automation",
                "coding_backend",
            ]
        )
        loop = _make_loop(tmp_path, mode=mode, domains=domains, monkeypatch=monkeypatch)
        snapshot = loop._build_tool_exposure_snapshot(
            initial_messages=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": str(case.get("input") or "")},
            ],
            tool_signal_text=None,
            force_final_response=False,
        )

        if mode != "off":
            assert set(snapshot.selected_domains) == set(case.get("expected_auto_domains", []))

        available_tools = set(loop.tools.tool_names)
        visible_tools = available_tools if snapshot.full_exposure else set(snapshot.ordered_tool_names)

        for tool_name in case.get("expect_tools_present", []):
            if tool_name not in available_tools:
                continue
            assert tool_name in visible_tools
        for tool_name in case.get("expect_tools_absent", []):
            if tool_name not in available_tools:
                continue
            assert tool_name not in visible_tools
