# ruff: noqa: F403, F405
from __future__ import annotations

from tests._tool_exposure_policy_testkit import *


def test_tool_exposure_off_uses_all_tools(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="off")
    selected = loop._select_tool_names_for_turn(_msgs("hello"))
    assert selected is None


def test_auto_web_signal_includes_web_tools(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto")
    selected = loop._select_tool_names_for_turn(_msgs("请搜索 https://example.com 相关信息"))
    assert selected is not None
    assert "web_fetch" in selected
    if "agent_browser" in loop.tools.tool_names:
        assert "agent_browser" in selected
    if "web_search" in loop.tools.tool_names:
        assert "web_search" in selected


def test_auto_web_signal_understands_natural_chinese_search_phrase(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto")
    selected = loop._select_tool_names_for_turn(_msgs("给我搜一个 ai 新闻"))
    assert selected is not None
    assert "web_fetch" in selected


def test_auto_web_signal_understands_check_latest_news_phrase(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto")
    selected = loop._select_tool_names_for_turn(_msgs("帮我查一下今天 AI 新闻"))
    assert selected is not None
    assert "web_fetch" in selected


def test_auto_code_signal_includes_code_tools(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto")
    selected = loop._select_tool_names_for_turn(_msgs("请修改这个 python 文件并运行 test"))
    assert selected is not None
    assert "read_file" in selected
    assert "exec" in selected
    assert "web_fetch" not in selected


def test_code_file_search_does_not_pull_web_bundle_from_generic_search_phrase(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto")
    selected = loop._select_tool_names_for_turn(_msgs("帮我找 loop.py 文件并读一下"))
    assert selected is not None
    assert "read_file" in selected
    assert "web_fetch" not in selected
    assert "web_search" not in selected
    assert "agent_browser" not in selected


def test_explicit_web_context_still_keeps_web_bundle_when_code_is_present(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto")
    selected = loop._select_tool_names_for_turn(_msgs("请搜索 https://example.com，并顺便看看 loop.py"))
    assert selected is not None
    assert "read_file" in selected
    assert "web_fetch" in selected


def test_core_bundle_includes_filesystem_tools(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", domains=["core"])
    selected = loop._select_tool_names_for_turn(_msgs("你好"))
    assert selected is not None
    assert "read_file" in selected
    assert "write_file" in selected
    assert "edit_file" in selected
    assert "list_dir" in selected


def test_auto_code_only_bundle_excludes_web(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", domains=["core", "coding_backend"])
    selected = loop._select_tool_names_for_turn(
        _msgs("请搜索 https://example.com 并修复 python 文件")
    )
    assert selected is not None
    assert "read_file" in selected
    assert "web_fetch" not in selected


def test_core_domain_keeps_local_filesystem_closure(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto")
    selected = loop._select_tool_names_for_turn(_msgs("hello"))
    assert selected is not None
    for name in ("read_file", "write_file", "edit_file", "list_dir", "exec"):
        assert name in selected


def test_message_send_request_includes_session_discovery_companions(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto")
    selected = loop._select_tool_names_for_turn(_msgs("你给 imessage 渠道发个消息测一下"))
    assert selected is not None
    assert "send_to_session" in selected
    assert "session_default" in selected
    assert "session_lookup" in selected
    assert "session_recent" in selected
    assert "session_resolve" in selected


def test_cross_channel_handoff_request_includes_send_to_session_and_discovery_tools(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto")
    selected = loop._select_tool_names_for_turn(_msgs("让 tg 那边的 bao 叫 imessage 那边去发消息"))
    assert selected is not None
    assert "send_to_session" in selected
    assert "session_default" in selected
    assert "session_lookup" in selected
    assert "session_recent" in selected
    assert "session_resolve" in selected


def test_exec_is_available_in_core_only_bundle(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto", domains=["core"])
    selected = loop._select_tool_names_for_turn(_msgs("你好"))
    assert selected is not None
    assert "exec" in selected


def test_auto_mode_uses_deterministic_core_closure_without_supplement(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto")
    selected = loop._select_tool_names_for_turn(_msgs("hello"))
    assert selected is not None
    assert selected == {
        "read_file",
        "write_file",
        "edit_file",
        "list_dir",
        "exec",
        "remember",
        "forget",
        "update_memory",
        "create_plan",
        "update_plan_step",
        "clear_plan",
        "spawn",
    }


def test_followup_short_phrase_reuses_previous_user_intent(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto")
    selected = loop._select_tool_names_for_turn(
        [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "请帮我搜索 AI 新闻"},
            {"role": "assistant", "content": "好的"},
            {"role": "user", "content": "这个呢"},
        ]
    )
    assert selected is not None
    assert "web_fetch" in selected


def test_acknowledgement_does_not_reuse_previous_user_intent(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path, mode="auto")
    selected = loop._select_tool_names_for_turn(
        [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "请帮我搜索 AI 新闻"},
            {"role": "assistant", "content": "好的"},
            {"role": "user", "content": "好的"},
        ]
    )
    assert selected is not None
    assert "web_fetch" not in selected
