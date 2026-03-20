"""Subagent progress status formatting tests."""

import time

from bao.agent.subagent import TaskStatus
from bao.agent.tools.task_status import _format_brief, _format_detailed
from tests._subagent_progress_testkit import pytest

pytest_plugins = ("tests._subagent_progress_testkit",)
pytestmark = [pytest.mark.integration, pytest.mark.slow]


def test_format_status_basic():
    st = TaskStatus(
        task_id="t1",
        label="research",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        iteration=5,
        tool_steps=3,
        phase="tool:web_fetch",
    )
    out = _format_detailed(st)
    assert "t1" in out
    assert "research" in out
    assert "5/20" in out
    assert "3 tools" in out
    assert "tool:web_fetch" in out


def test_format_status_stale_warning():
    st = TaskStatus(
        task_id="t1",
        label="stuck",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
        phase="thinking",
    )
    st.updated_at = time.time() - 150
    out = _format_detailed(st)
    assert "\u26a0\ufe0f" in out
    assert "no update" in out.lower()


def test_format_status_no_warning_when_completed():
    st = TaskStatus(
        task_id="t1",
        label="done",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="completed",
        phase="completed",
    )
    st.updated_at = time.time() - 300
    out = _format_brief(st)
    assert "\u26a0\ufe0f" not in out


def test_format_status_shows_result_summary_on_completed():
    st = TaskStatus(
        task_id="t1",
        label="research",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="completed",
        phase="completed",
        result_summary="Found 3 relevant papers on transformer architecture.",
    )
    out = _format_detailed(st)
    assert "result:" in out
    assert "Found 3 relevant papers" in out


def test_format_status_shows_result_summary_on_failed():
    st = TaskStatus(
        task_id="t1",
        label="deploy",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="failed",
        phase="failed",
        result_summary="Error: connection refused on port 5432",
    )
    out = _format_detailed(st)
    assert "result:" in out
    assert "connection refused" in out


def test_format_status_truncates_long_summary():
    long_summary = "X" * 400
    st = TaskStatus(
        task_id="t1",
        label="big",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="completed",
        phase="completed",
        result_summary=long_summary,
    )
    out = _format_detailed(st)
    assert "..." in out
    result_idx = out.index("result:")
    summary_part = out[result_idx + 8 :]
    assert summary_part.strip().startswith("X" * 300)
    assert summary_part.strip().endswith("...")


def test_format_status_no_summary_for_running():
    st = TaskStatus(
        task_id="t1",
        label="active",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
        phase="thinking",
        result_summary="partial result",
    )
    out = _format_brief(st)
    assert "result:" not in out


def test_format_status_sanitizes_pipe_in_result_summary():
    st = TaskStatus(
        task_id="t1",
        label="report",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="completed",
        phase="completed",
        result_summary="A|B|C",
    )
    out = _format_brief(st)
    assert "A/B/C" in out
    assert "A|B|C" not in out


def test_format_status_sanitizes_pipe_in_recent_actions():
    st = TaskStatus(
        task_id="t1",
        label="running",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
    )
    st.recent_actions = ["exec(ls|wc)"]
    out = _format_detailed(st)
    assert "exec(ls/wc)" in out
    assert "exec(ls|wc)" not in out


def test_format_status_shows_recent_actions_for_running():
    st = TaskStatus(
        task_id="t1",
        label="research",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
    )
    st.recent_actions = ["web_search(q)", "read_file(x.py)", "exec(ls)", "write_file(out.txt)"]
    output = _format_detailed(st)
    assert "recent:" in output
    assert "read_file(x.py)" in output
    assert "exec(ls)" in output
    assert "write_file(out.txt)" in output
    assert "web_search(q)" not in output


def test_format_status_no_recent_actions_for_running():
    st = TaskStatus(
        task_id="t1",
        label="test",
        task_description="d",
        origin={"channel": "tg", "chat_id": "1"},
        status="running",
    )
    output = _format_detailed(st)
    assert "recent:" not in output

