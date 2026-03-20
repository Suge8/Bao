# ruff: noqa: F403, F405
from __future__ import annotations

from bao.agent._loop_run_models import FinalizeToolObservabilityRequest
from tests._tool_exposure_policy_testkit import *


def test_available_now_uses_deterministic_closure_order_for_web(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto")
    selected = loop._select_tool_names_for_turn(_msgs("给我搜一个 ai 新闻"))
    assert selected is not None
    ordered = loop._order_selected_tool_names(
        selected, loop._build_tool_route_text(_msgs("给我搜一个 ai 新闻"))
    )
    assert ordered[:2] == ["read_file", "write_file"]
    assert "web_fetch" in ordered
    if "web_search" in selected:
        assert "web_search" in ordered
        assert ordered.index("web_search") < ordered.index("web_fetch")


def test_coding_route_uses_core_then_coding_closure_order(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto")
    selected = loop._select_tool_names_for_turn(_msgs("请修改这个 python 文件并运行 test"))
    assert selected is not None
    ordered = loop._order_selected_tool_names(
        selected, loop._build_tool_route_text(_msgs("请修改这个 python 文件并运行 test"))
    )
    assert ordered[:5] == ["read_file", "write_file", "edit_file", "list_dir", "exec"]
    assert ordered[-1] == "coding_agent"


def test_dynamic_metadata_tool_no_longer_enters_exposure_without_domain_membership(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", domains=["core"])
    loop.tools.register(
        _MetadataOnlyTool(),
        metadata=ToolMetadata(
            bundle="core",
            short_hint="Look up live weather or forecasts.",
            aliases=("weather lookup",),
            keyword_aliases=("weather", "forecast"),
            auto_callable=True,
            summary="Look up live weather or forecasts.",
        ),
    )
    selected = loop._select_tool_names_for_turn(_msgs("查一下今天的 weather forecast"))
    assert selected is not None
    assert "acme_lookup" not in selected


def test_force_final_response_does_not_inject_available_now(tmp_path: Path) -> None:
    provider = DummyProvider()
    loop = AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path, config=Config())
    messages = [
        {"role": "system", "content": "test"},
        {"role": "user", "content": "给我搜一个 ai 新闻"},
    ]

    asyncio.run(
        loop._chat_once_with_selected_tools(
            ChatOnceRequest(
                messages=messages,
                initial_messages=messages,
                iteration=1,
                on_progress=None,
                current_task_ref=None,
                tool_signal_text=None,
                force_final_response=True,
                counters=_ToolObservabilityCounters(),
            )
        )
    )

    assert provider.last_request is not None
    system_prompt = provider.last_request.messages[0]["content"]
    assert "## Available Now" not in system_prompt


def test_observability_includes_routing_fields(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", domains=["core"])
    loop._finalize_tool_observability(
        FinalizeToolObservabilityRequest(
            tool_budget={
                "offloaded_count": 0,
                "offloaded_chars": 0,
                "clipped_count": 0,
                "clipped_chars": 0,
            },
            counters=_ToolObservabilityCounters(),
            tools_used=[],
            total_errors=0,
        )
    )
    obs = loop._last_tool_observability
    assert obs["routing_mode"] == "auto"
    assert obs["routing_full_exposure"] is False


def test_registry_empty_allowlist_returns_no_tools(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="off")
    definitions = loop.tools.get_definitions(names=set())
    assert definitions == []
