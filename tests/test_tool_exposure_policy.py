from __future__ import annotations

from pathlib import Path
from typing import Any

from bao.agent.loop import (
    _ROUTE_RESCUE_TOOLS,
    _TOOL_ROUTE_MAX_ESCALATIONS,
    _TOOL_ROUTE_TOPK_TIER0,
    AgentLoop,
)
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


def _msgs(user_text: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": "test"},
        {"role": "user", "content": user_text},
    ]


# ---------------------------------------------------------------------------
# off mode — unchanged semantics
# ---------------------------------------------------------------------------


def test_tool_exposure_off_uses_all_tools(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="off", bundles=["core", "web", "desktop", "code"])
    selected = loop._select_tool_names_for_turn(_msgs("hello"))
    assert selected is None


# ---------------------------------------------------------------------------
# auto mode — scored routing
# ---------------------------------------------------------------------------


def test_auto_web_signal_includes_web_tools(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", bundles=["core", "web", "code"])
    selected = loop._select_tool_names_for_turn(_msgs("请搜索 https://example.com 相关信息"))
    assert selected is not None
    assert "web_fetch" in selected
    # web_search only registered when search API key is configured
    if "web_search" in loop.tools.tool_names:
        assert "web_search" in selected
    assert "message" in selected  # rescue


def test_auto_code_signal_includes_code_tools(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", bundles=["core", "web", "code"])
    selected = loop._select_tool_names_for_turn(_msgs("请修改这个 python 文件并运行 test"))
    assert selected is not None
    assert "read_file" in selected
    assert "exec" in selected
    assert "web_fetch" not in selected


def test_auto_code_only_bundle_excludes_web(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", bundles=["core", "code"])
    selected = loop._select_tool_names_for_turn(
        _msgs("请搜索 https://example.com 并修复 python 文件")
    )
    assert selected is not None
    assert "message" in selected
    assert "read_file" in selected
    assert "web_fetch" not in selected


# ---------------------------------------------------------------------------
# rescue set — always included when bundle allows
# ---------------------------------------------------------------------------


def test_rescue_tools_always_included(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", bundles=["core", "web", "code"])
    selected = loop._select_tool_names_for_turn(_msgs("hello"))
    assert selected is not None
    for rescue_name in _ROUTE_RESCUE_TOOLS:
        if rescue_name in loop.tools.tool_names:
            assert rescue_name in selected, f"rescue tool '{rescue_name}' missing"


def test_exec_is_available_in_core_only_bundle(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", bundles=["core"])
    selected = loop._select_tool_names_for_turn(_msgs("你好"))
    assert selected is not None
    assert "exec" in selected


# ---------------------------------------------------------------------------
# exposure_level tiers
# ---------------------------------------------------------------------------


def test_tier0_limits_tool_count(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", bundles=["core", "web", "desktop", "code"])
    selected = loop._select_tool_names_for_turn(_msgs("hello"), exposure_level=0)
    assert selected is not None
    # tier0 topK + rescue — should not exceed topK + rescue size
    max_expected = _TOOL_ROUTE_TOPK_TIER0 + len(_ROUTE_RESCUE_TOOLS)
    assert len(selected) <= max_expected


def test_tier1_includes_more_tools(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", bundles=["core", "web", "desktop", "code"])
    tier0 = loop._select_tool_names_for_turn(_msgs("hello"), exposure_level=0)
    tier1 = loop._select_tool_names_for_turn(_msgs("hello"), exposure_level=1)
    assert tier0 is not None
    assert tier1 is not None
    assert len(tier1) >= len(tier0)


def test_max_escalation_returns_none(tmp_path: Path) -> None:
    """At max escalation level, _select returns None => full exposure."""
    loop = _make_loop(tmp_path, mode="auto", bundles=["core", "web", "code"])
    selected = loop._select_tool_names_for_turn(
        _msgs("hello"), exposure_level=_TOOL_ROUTE_MAX_ESCALATIONS
    )
    assert selected is None


# ---------------------------------------------------------------------------
# tool_intent_score
# ---------------------------------------------------------------------------


def test_intent_score_high_for_explicit_actions(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", bundles=["core"])
    score = loop._tool_intent_score("请帮我搜索 https://example.com 然后读取文件")
    assert score >= 0.65


def test_intent_score_low_for_chat(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", bundles=["core"])
    score = loop._tool_intent_score("你好，今天天气怎么样？")
    assert score < 0.3


# ---------------------------------------------------------------------------
# score_tool_for_routing
# ---------------------------------------------------------------------------


def test_score_tool_web_signal_boosts_web_tools(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", bundles=["core", "web"])
    user_text = "search https://example.com"
    tokens = loop._route_tokens(user_text)
    web_score = loop._score_tool_for_routing("web_fetch", user_text, tokens)
    core_score = loop._score_tool_for_routing("message", user_text, tokens)
    assert web_score > core_score


def test_score_tool_unknown_bundle_returns_negative(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", bundles=["core"])
    score = loop._score_tool_for_routing("nonexistent_tool", "hello", set())
    assert score < 0


# ---------------------------------------------------------------------------
# observability fields
# ---------------------------------------------------------------------------


def test_observability_includes_routing_fields(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", bundles=["core"])
    from bao.agent.loop import _ToolObservabilityCounters

    loop._finalize_tool_observability(
        tool_budget={
            "offloaded_count": 0,
            "offloaded_chars": 0,
            "clipped_count": 0,
            "clipped_chars": 0,
        },
        counters=_ToolObservabilityCounters(),
        tools_used=[],
        total_errors=0,
        routing_tier=1,
        escalation_count=1,
        escalation_reasons=["intent_no_tool"],
    )
    obs = loop._last_tool_observability
    assert obs["routing_tier_final"] == 1
    assert obs["routing_escalation_count"] == 1
    assert obs["routing_escalation_reasons"] == ["intent_no_tool"]
    assert obs["routing_full_exposure"] is False


# ---------------------------------------------------------------------------
# registry helper — empty allowlist
# ---------------------------------------------------------------------------


def test_registry_empty_allowlist_returns_no_tools(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="off", bundles=["core", "web", "desktop", "code"])
    definitions = loop.tools.get_definitions(names=set())
    assert definitions == []
