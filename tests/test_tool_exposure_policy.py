from __future__ import annotations

from pathlib import Path
from typing import Any

from bao.agent.loop import AgentLoop
from bao.bus.queue import MessageBus
from bao.config.schema import Config, ToolExposureConfig, ToolsConfig
from bao.providers.base import LLMProvider, LLMResponse


class DummyProvider(LLMProvider):
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


def _make_loop(tmp_path: Path, mode: str, bundles: list[str]) -> AgentLoop:
    cfg = Config(tools=ToolsConfig(tool_exposure=ToolExposureConfig(mode=mode, bundles=bundles)))
    return AgentLoop(bus=MessageBus(), provider=DummyProvider(), workspace=tmp_path, config=cfg)


def test_tool_exposure_off_uses_all_tools(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="off", bundles=["core", "web", "desktop", "code"])
    selected = loop._select_tool_names_for_turn(
        [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "hello"},
        ]
    )
    assert selected is None


def test_tool_exposure_auto_respects_bundle_switch(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", bundles=["core", "code"])
    selected = loop._select_tool_names_for_turn(
        [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "请搜索 https://example.com 并修复 python 文件"},
        ]
    )
    assert selected is not None
    assert "message" in selected
    assert "read_file" in selected
    assert "web_fetch" not in selected


def test_tool_exposure_auto_routes_web_and_code(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", bundles=["core", "web", "code"])

    web_selected = loop._select_tool_names_for_turn(
        [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "请搜索 https://example.com 相关信息"},
        ]
    )
    assert web_selected is not None
    assert "message" in web_selected
    assert "web_fetch" in web_selected
    assert "read_file" not in web_selected

    code_selected = loop._select_tool_names_for_turn(
        [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "请修改这个 python 文件并运行 test"},
        ]
    )
    assert code_selected is not None
    assert "message" in code_selected
    assert "read_file" in code_selected
    assert "web_fetch" not in code_selected


def test_check_tasks_json_respects_core_bundle(tmp_path: Path) -> None:
    loop_core = _make_loop(tmp_path, mode="auto", bundles=["core"])
    selected_core = loop_core._select_tool_names_for_turn(
        [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "hello"},
        ]
    )
    assert selected_core is not None
    assert "check_tasks_json" in selected_core

    loop_no_core = _make_loop(tmp_path, mode="auto", bundles=["code"])
    selected_no_core = loop_no_core._select_tool_names_for_turn(
        [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "hello"},
        ]
    )
    assert selected_no_core is not None
    assert "check_tasks_json" not in selected_no_core


def test_registry_empty_allowlist_returns_no_tools(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="off", bundles=["core", "web", "desktop", "code"])
    definitions = loop.tools.get_definitions(names=set())
    assert definitions == []
