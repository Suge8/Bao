from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from bao.agent.loop import AgentLoop
from bao.bus.queue import MessageBus
from bao.config.schema import Config, ToolExposureConfig, ToolsConfig
from bao.providers.base import LLMProvider, LLMResponse


class DummyProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(api_key=None, api_base=None)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        on_progress=None,
        **kwargs: Any,
    ) -> LLMResponse:
        del messages, tools, model, max_tokens, temperature, on_progress, kwargs
        return LLMResponse(content="ok", finish_reason="stop")

    def get_default_model(self) -> str:
        return "dummy/model"


def _load_cases() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parents[1] / "docs" / "tool-exposure-cases.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("cases", []))


def _make_loop(tmp_path: Path, *, mode: str, bundles: list[str], monkeypatch: pytest.MonkeyPatch) -> AgentLoop:
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    cfg = Config(tools=ToolsConfig(tool_exposure=ToolExposureConfig(mode=mode, bundles=bundles)))
    return AgentLoop(bus=MessageBus(), provider=DummyProvider(), workspace=tmp_path, config=cfg)


@pytest.mark.parametrize("case", _load_cases(), ids=lambda item: str(item["id"]))
def test_tool_exposure_cases_match_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: dict[str, Any],
) -> None:
    mode = str(case.get("expected_mode") or "auto")
    bundles = list(case.get("run_with_bundles") or ["core", "web", "desktop", "code"])
    loop = _make_loop(tmp_path, mode=mode, bundles=bundles, monkeypatch=monkeypatch)
    snapshot = loop._build_tool_exposure_snapshot(
        initial_messages=[
            {"role": "system", "content": "test"},
            {"role": "user", "content": str(case.get("input") or "")},
        ],
        tool_signal_text=None,
        exposure_level=0,
        force_final_response=False,
    )

    if mode != "off":
        assert set(snapshot.selected_bundles) == set(case.get("expected_auto_bundles", []))

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
